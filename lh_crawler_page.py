import os
import re
import time
import requests
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

def collect_lh_file_urls():
    # ── 설정 ─────────────────────────────────────────────────
    BASE_URL     = "https://apply.lh.or.kr"
    LIST_URL     = BASE_URL + "/lhapply/apply/wt/wrtanc/selectWrtancList.do?viewType=srch"
    DOWNLOAD_URL = BASE_URL + "/lhapply/lhFile.do"
    DOWNLOAD_DIR = "./downloads"
    HEADERS      = {"User-Agent": "Mozilla/5.0"}

    # 프로젝트 루트에 있는 chromedriver.exe 경로
    DRIVER_PATH = os.path.join(os.getcwd(), "chromedriver.exe")
    
    # 다운로드 폴더 준비
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    # 이미 다운로드된 파일 목록 기억
    already_downloaded = set(os.listdir(DOWNLOAD_DIR))

    # 다운로드 링크 저장할 list 변수
    url_list = []

    # 드라이버 초기화 함수 - Selenium WebDriver 준비
    def init_driver():
        chrome_opts = Options()
        chrome_opts.add_argument("--headless")            # 창 숨김 모드
        chrome_opts.add_argument("--disable-gpu")
        chrome_opts.add_argument(f"user-agent={HEADERS['User-Agent']}")
        driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=chrome_opts)
        wait = WebDriverWait(driver, 10)
        return driver, wait
    
    # 파일명에서 위험 문자를 제거 후 글자 제한
    def sanitize_filename(name, max_length=25):
        cleaned = re.sub(r'[\\/*?:"<>|]', '_', name)
        return cleaned[:max_length]

    # 공고 검색 버튼 누르는 함수
    def search_list():
        Select(driver.find_element(By.ID, "srchTypeAisTpCd")).select_by_value("05")
        WebDriverWait(driver, 5).until(EC.visibility_of_element_located((By.ID, "aisTpCdData05")))
        Select(driver.find_element(By.ID, "aisTpCdData05")).select_by_value("")
        Select(driver.find_element(By.ID, "cnpCd")).select_by_value("")
        Select(driver.find_element(By.ID, "panSs")).select_by_value("")

        end_date = datetime.today().date()
        start_date = end_date - timedelta(days=5*365+1)
        print(f"📅 조회 기간: {start_date} ~ {end_date}")

        start_input = driver.find_element(By.ID, "startDt")
        start_input.send_keys(Keys.CONTROL, "a")
        start_input.send_keys(Keys.DELETE)
        start_input.send_keys(start_date.strftime("%Y-%m-%d"))

        end_input = driver.find_element(By.ID, "endDt")
        end_input.send_keys(Keys.CONTROL, "a")
        end_input.send_keys(Keys.DELETE)
        end_input.send_keys(end_date.strftime("%Y-%m-%d"))
        
        try:
            btn = wait.until(EC.element_to_be_clickable((By.ID, "btnSah")))
            btn.click()
            print("▶ '검색' 버튼 클릭 성공")
        except Exception as e:
            print("▶ '검색' 버튼 클릭 실패:", e)
        time.sleep(3)  # 조회 후 로딩 대기

    # 초기 드라이버 실행
    driver, wait = init_driver()

    # ── 2) 공고 리스트 페이지 열기 ─────────────────────────────
    driver.get(LIST_URL)
    time.sleep(1)

    search_list()

    # 마지막 페이지 수 확인
    last_page_btn = driver.find_element(By.CSS_SELECTOR, ".bbs_arr.pgeR2")
    last_page_onclick = last_page_btn.get_attribute("onclick")
    MAX_PAGE = int(last_page_onclick.split("(")[1].split(")")[0])
    print(f"\n 전체 페이지 수: {MAX_PAGE}")


    # ── 4) 각 공고 상세페이지 순회 & “공고문” 파일만 다운로드 ───────────
    session = requests.Session()
    session.headers.update(HEADERS)

    for page in range(1, MAX_PAGE + 1):
        print(f"\n📄 현재 페이지: {page} \n 드라이버 재시작: 주기적 세션 리셋")
        driver.quit()
        driver, wait = init_driver()
        driver.get(LIST_URL)
        time.sleep(1)
        search_list()

        # ——— 페이지 네비게이션 수정된 부분 ———
        page_found = False
        retry = 0
        while not page_found and retry < 10:
            # (1) 현재 보이는 페이지 번호(링크 + strong) 모두 수집
            page_btns = driver.find_elements(By.CSS_SELECTOR, ".bbs_pge_num")
            for btn in page_btns:
                if btn.text.strip() == str(page):
                    # 링크(a)든 strong이든 클릭
                    try:
                        btn.click()
                    except:
                        driver.execute_script("arguments[0].click();", btn)
                    print(f"✅ {page}페이지 버튼 클릭 성공")
                    page_found = True
                    break

            # (2) 클릭 성공하면 탈출
            if page_found:
                break

            # (3) 1~10페이지면 블록 이동 필요 없음
            if page <= 10:
                print(f"⚠️ {page}페이지 버튼이 보이지 않습니다. (1~10페이지는 블록 전환 불필요)")
                break

            # (4) 11페이지 이상: 다음 블록(pgeR1) 클릭
            print("➡️ 다음 페이지 블록 전환: pgeR1 클릭")
            try:
                driver.find_element(By.CSS_SELECTOR, "a.bbs_arr.pgeR1").click()
                time.sleep(1)
            except Exception as e:
                print(f"⚠️ pgeR1 버튼 클릭 실패: {e}")
                break

            retry += 1
        # ————————————————

        # (5) 페이지 로딩 대기
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.wrtancInfoBtn"))
        )

        # ── 공고 행 가져오기 ───────────────────────────────────
        row_links = driver.find_elements(By.CSS_SELECTOR, "a.wrtancInfoBtn")
        print(f"  - 공고 수: {len(row_links)}")

        for idx in range(len(row_links)):
            try:
                row_links = driver.find_elements(By.CSS_SELECTOR, "a.wrtancInfoBtn")
                link = row_links[idx]
                wrtan_no = link.get_attribute("data-id1")
                print(f"\n[{idx+1}] 공고 클릭: {wrtan_no}")
                link.click()
                time.sleep(2)

                try:
                    # 공고일 추출
                    pub_date_text = driver.find_element(By.XPATH, "//li[strong[text()='공고일']]").text
                    pub_date = pub_date_text.replace("공고일", "").strip().replace(".", "")  # 예: 20250430
                except:
                    pub_date = datetime.today().strftime("%Y%m%d")

                # 상세페이지 내 공고문 파일 수집
                try:
                    dl = driver.find_element(By.CSS_SELECTOR, "dl.col_red")
                    dl.find_element(By.XPATH, ".//dt[text()='공고문']")
                    list_items = dl.find_elements(By.XPATH, ".//dd//ul[contains(@class,'file')]/li")
                except Exception:
                    print("    ⚠️ 공고문 섹션 없음, 건너뜀")
                    driver.back()
                    time.sleep(1)
                    continue

                print(f"    ▶ 공고문 파일 수: {len(list_items)}")

                # C단계 안에서 각 li 처리 시
                for li in list_items:
                    try:
                        a_dl = li.find_element(By.XPATH, "./a[1]")
                        filename = a_dl.text.strip()
                        name_part, ext = os.path.splitext(filename)
                        short_name = sanitize_filename(name_part)

                        # 필터: '공고' 포함 + .pdf

                        if '공고' not in filename or not filename.split(".")[-1] =='pdf':
                            print(f"    ⚠️ 조건 불일치 → 건너뜀: {filename}")
                            continue

                        file_id = a_dl.get_attribute("href").split("'")[1]
                        file_url = f"{DOWNLOAD_URL}?fileid={file_id}"
                        safe_filename = f"{wrtan_no}_{pub_date}_{short_name}{ext}"
                        save_path = os.path.join(DOWNLOAD_DIR, safe_filename)

                        if safe_filename in already_downloaded:
                            print(f"    ⏭️ 이미 다운로드됨 → {safe_filename}")

                        else:
                            resp = session.get(file_url, headers={
                                "Referer": driver.current_url,
                                "User-Agent": HEADERS["User-Agent"]
                            })

                            resp.raise_for_status()
                            with open(save_path, "wb") as fw:
                                fw.write(resp.content)

                            print(f"✅ 다운로드 완료 → {save_path}")
                            already_downloaded.add(safe_filename)

                        url_list.append((file_url, {"wrtan_no": wrtan_no, "pub_date": pub_date, "filename": filename}))

                    except Exception as e:
                        print(f"    ⚠️ 파일 다운로드 실패: {e}")

                driver.back()
                WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "btnSah")))
                time.sleep(1)

            except Exception as e:
                print(f"    ⚠️ [{idx+1}] 공고 처리 실패: {e} → 건너뜁니다.")
                continue

    # ── 5) 마무리 ───────────────────────────────────────────────
    driver.quit()
    print("✅ 모든 공고문 다운로드 완료")
    return url_list

if __name__ == "__main__":
    collected_urls = collect_lh_file_urls()
    print(f"\n⭐ 최종 수집된 파일 수: {len(collected_urls)}개")

