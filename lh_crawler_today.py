import os
import re
import time
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys


def collect_lh_file_urls():
    BASE_URL = "https://apply.lh.or.kr"
    LIST_URL = BASE_URL + "/lhapply/apply/wt/wrtanc/selectWrtancList.do?viewType=srch"
    DOWNLOAD_URL = BASE_URL + "/lhapply/lhFile.do"
    DOWNLOAD_DIR = "./downloads"
    HEADERS = {"User-Agent": "Mozilla/5.0"}
    DRIVER_PATH = os.path.join(os.getcwd(), "chromedriver.exe")

    # (1) 다운로드 폴더 & 이미 받은 파일 목록 준비
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    already_downloaded = set(os.listdir(DOWNLOAD_DIR))
    url_list = []

    # (2) 드라이버 초기화
    def init_driver():
        chrome_opts = Options()
        chrome_opts.add_argument("--headless")
        chrome_opts.add_argument("--disable-gpu")
        chrome_opts.add_argument(f"user-agent={HEADERS['User-Agent']}")
        driver = webdriver.Chrome(service=Service(DRIVER_PATH), options=chrome_opts)
        wait = WebDriverWait(driver, 10)
        return driver, wait

    # (3) 파일명 안전하게
    def sanitize_filename(name, max_length=25):
        cleaned = re.sub(r'[\\/*?:"<>|]', '_', name)
        return cleaned[:max_length]

    driver, wait = init_driver()
    driver.get(LIST_URL)
    time.sleep(1)

    # — 1) 오늘자만 필터링 —
    today = datetime.today().date()
    print(f"📅 오늘 날짜 기준 조회: {today}")

    # 유형 설정
    Select(driver.find_element(By.ID, "srchTypeAisTpCd")).select_by_value("05")
    wait.until(EC.visibility_of_element_located((By.ID, "aisTpCdData05")))
    Select(driver.find_element(By.ID, "aisTpCdData05")).select_by_value("")
    Select(driver.find_element(By.ID, "cnpCd")).select_by_value("")
    Select(driver.find_element(By.ID, "panSs")).select_by_value("")

    # 날짜 필터
    # startDt 필드에 today 설정
    start_input = driver.find_element(By.ID, "startDt")
    driver.execute_script(
        "arguments[0].removeAttribute('readonly'); arguments[0].value = arguments[1];",
        start_input,
        today.strftime("%Y-%m-%d")
    )

    # endDt 필드에 today 설정
    end_input = driver.find_element(By.ID, "endDt")
    driver.execute_script(
        "arguments[0].removeAttribute('readonly'); arguments[0].value = arguments[1];",
        end_input,
        today.strftime("%Y-%m-%d")
    )

    btn = wait.until(EC.element_to_be_clickable((By.ID, "btnSah")))
    btn.click()

    # 검색 버튼 클릭
    wait.until(EC.element_to_be_clickable((By.ID, "btnSah"))).click()
    time.sleep(3)

    # — 2) 오늘자 공고 확인 & 없으면 종료 —
    row_links = driver.find_elements(By.CSS_SELECTOR, "a.wrtancInfoBtn")
    if not row_links:
        print("❌ 오늘자 공고가 없습니다. 종료합니다.")
        driver.quit()
        return url_list

    print(f"▶ 오늘자 공고 수: {len(row_links)}건")
    session = requests.Session()
    session.headers.update(HEADERS)

    # — 3) 한 페이지만 순회하며 공고문 다운로드 —
    for idx in range(len(row_links)):
        # ❗️ 매 반복마다 fresh 요소 리스트를 다시 가져옵니다
        row_links = driver.find_elements(By.CSS_SELECTOR, "a.wrtancInfoBtn")
        link = row_links[idx]
        wrtan_no = link.get_attribute("data-id1")
        print(f"\n[{idx+1}] 공고 클릭: {wrtan_no}")
        link.click()
        time.sleep(2)

        # 공고일
        try:
            pub_date_text = driver.find_element(By.XPATH, "//li[strong[text()='공고일']]").text
            pub_date = pub_date_text.replace("공고일", "").strip().replace(".", "")
        except:
            pub_date = today.strftime("%Y%m%d")

        # 공고문 리스트
        try:
            dl = driver.find_element(By.CSS_SELECTOR, "dl.col_red")
            items = dl.find_elements(By.XPATH, ".//dt[text()='공고문']/following-sibling::dd//li")
        except:
            print("    ⚠️ 공고문 섹션 없음, 건너뜁니다.")
            driver.back()
            time.sleep(1)
            continue

        print(f"    ▶ 공고문 파일 수: {len(items)}")
        for li in items:
            a = li.find_element(By.TAG_NAME, "a")
            filename = a.text.strip()
            name_part, ext = os.path.splitext(filename)
            if '공고' not in filename or ext.lower() != '.pdf':
                continue
            short_name = sanitize_filename(name_part)
            file_id = a.get_attribute("href").split("'")[1]
            file_url = f"{DOWNLOAD_URL}?fileid={file_id}"
            safe_filename = f"{wrtan_no}_{pub_date}_{short_name}{ext}"
            save_path = os.path.join(DOWNLOAD_DIR, safe_filename)

            if safe_filename in already_downloaded:
                print(f"    ⏭️ 이미 다운로드됨 → {safe_filename}")
            else:
                resp = session.get(file_url, headers={"Referer": driver.current_url, "User-Agent": HEADERS["User-Agent"]})
                resp.raise_for_status()
                with open(save_path, "wb") as fw:
                    fw.write(resp.content)
                print(f"✅ 다운로드 완료 → {save_path}")
                already_downloaded.add(safe_filename)

            url_list.append((file_url, {"wrtan_no": wrtan_no, "pub_date": pub_date, "filename": filename}))

        # 뒤로가기
        driver.back()
        wait.until(EC.element_to_be_clickable((By.ID, "btnSah")))
        time.sleep(1)

    driver.quit()
    print("✅ 오늘자 공고문 다운로드 완료")
    return url_list

if __name__ == "__main__":
    collected_urls = collect_lh_file_urls()
    print(f"\n⭐ 최종 수집된 파일 수: {len(collected_urls)}개")
