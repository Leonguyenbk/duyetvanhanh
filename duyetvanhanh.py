import time, traceback, threading, sys, json, re, os
import tkinter as tk
from tkinter import ttk, messagebox

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, ElementClickInterceptedException, JavascriptException,
    StaleElementReferenceException, NoSuchElementException, ElementNotInteractableException,
    NoSuchWindowException
)

# --- Functions from the original script ---

def wait_query_done(driver, timeout=30, ajax_wait=5):

    def wait_loading_mask(driver, timeout=10):
        """Chờ lớp loading mask của jQuery biến mất"""
        try:
            WebDriverWait(driver, timeout).until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, "div.jquery-loading-modal_bg")
                )
            )
        except:
            pass

        # DỌN loading mask còn sót (opacity 0 vẫn block click)
        try:
            driver.execute_script("""
                document.querySelectorAll('div.jquery-loading-modal_bg')
                        .forEach(e => e.remove());
            """)
        except:
            pass

    # --- BẮT ĐẦU LOGIC GỐC ---
    end_time = time.time() + timeout

    # Đảm bảo jQuery tồn tại
    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.jQuery !== undefined;")
        )
    except:
        # Dù sao cũng phải chờ loading mask
        wait_loading_mask(driver)
        return

    # Chờ AJAX bắt đầu
    phase1_end = time.time() + ajax_wait
    saw_ajax = False
    while time.time() < phase1_end:
        try:
            active = driver.execute_script("return jQuery.active;")
            if active > 0:
                saw_ajax = True
                break
        except:
            break
        time.sleep(0.1)

    if not saw_ajax:
        wait_loading_mask(driver)
        return

    # Chờ AJAX kết thúc
    while time.time() < end_time:
        try:
            active = driver.execute_script("return jQuery.active;")
            if active == 0:
                break
        except:
            break
        time.sleep(0.1)

    # 🔥 Cuối cùng, CHỜ loading mask của hệ thống biến mất
    wait_loading_mask(driver)

def close_dangky_modal(driver, timeout=10):
    wait = WebDriverWait(driver, timeout)
    MODAL_CSS = "div.modal.modal-fullscreen[id^='mdlDangKyWizard-']"
    try:
        modal = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, MODAL_CSS))
        )
    except:
        print("ℹ️ Không tìm thấy modal DangKyWizard để đóng.")
        return
    close_btn = modal.find_element(By.CSS_SELECTOR, "div.modal-header > button.close")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", close_btn)
    close_btn.click()
    print("👉 Đã nhấn nút close trên modal DangKyWizard")
    WebDriverWait(driver, timeout).until(
        EC.invisibility_of_element_located((By.CSS_SELECTOR, MODAL_CSS))
    )
    print("✅ Modal DangKyWizard đã đóng")

def handle_jconfirm_popups(driver, timeout_first=20, timeout_second=5):
    wait = WebDriverWait(driver, timeout_first)
    POPUP_CSS = "body > div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"
    BTN_ORANGE_CSS = POPUP_CSS + " div.jconfirm-buttons > button.btn.btn-orange"

    # 1️⃣ POPUP ĐẦU TIÊN — nút cam
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, POPUP_CSS)))
    except:
        return  # không có popup nào
    print("✅ Popup jConfirm đầu tiên đã xuất hiện")

    btn_cam = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, BTN_ORANGE_CSS))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn_cam)
    btn_cam.click()
    print("👉 Đã nhấn nút cam (Đồng ý) ở popup đầu tiên")

    WebDriverWait(driver, 10).until(
        EC.invisibility_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
    )
    print("✅ Popup jConfirm đầu tiên đã biến mất")

    # 2️⃣ POPUP THỨ HAI — xử lý ngay, KHÔNG QUAN TÂM NỘI DUNG
    wait2 = WebDriverWait(driver, timeout_second)
    try:
        wait2.until(EC.presence_of_element_located((By.CSS_SELECTOR, POPUP_CSS)))
    except:
        print("ℹ️ Không có popup thứ 2.")
        return

    print("⚠️ Popup thứ 2 đã xuất hiện — xử lý luôn")

    # Nhấn Đồng Ý popup thứ 2
    try:
        btn_ok2 = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                POPUP_CSS + " div.jconfirm-buttons > button"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn_ok2)
        btn_ok2.click()
        print("👉 Đã nhấn Đồng ý popup thứ 2")
    except:
        print("❌ Không tìm thấy nút Đồng ý của popup thứ 2")

    # Chờ popup đóng
    try:
        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
        )
        print("✅ Popup thứ 2 đã biến mất")
    except:
        print("⚠️ Popup thứ 2 không biến mất đúng thời gian")

    # 3️⃣ ĐÓNG WIZARD NẾU CÒN MỞ
    try:
        MODAL_CSS = "div.modal.modal-fullscreen[id^='mdlDangKyWizard-']"
        modal = driver.find_element(By.CSS_SELECTOR, MODAL_CSS)

        if modal.is_displayed():
            close_btn = modal.find_element(By.CSS_SELECTOR, "div.modal-header > button.close")
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", close_btn)
            close_btn.click()

            WebDriverWait(driver, 10).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, MODAL_CSS))
            )
            print("🔒 Wizard đã được đóng sau popup thứ 2")
        else:
            print("ℹ️ Wizard không hiển thị, bỏ qua.")
    except:
        print("ℹ️ Wizard đã đóng hoặc không tồn tại")

def handle_optional_jconfirm(driver, timeout=10):
    POPUP_CSS = "body > div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"
    BTN_CSS = POPUP_CSS + " div.jconfirm-buttons > button"
    wait_short = WebDriverWait(driver, timeout)
    try:
        wait_short.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
        )
    except:
        return False
    print("⚠️ Xuất hiện popup jConfirm khi chọn bản ghi")
    btn_ok = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, BTN_CSS))
    )
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn_ok)
    btn_ok.click()
    print("👉 Đã nhấn nút Đồng ý trong popup")
    WebDriverWait(driver, 10).until(
        EC.invisibility_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
    )
    print("✅ Popup đã biến mất")
    return True

def run_automation(username, password, maxa, base_url):
    """Main automation logic."""
    driver = None
    try:
        options = Options()
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach", True)
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 20)
        driver.get(base_url)

        wait.until(EC.presence_of_element_located((By.NAME, "username"))).send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.NAME, "password").send_keys(Keys.ENTER)

        messagebox.showinfo("Info", "Đăng nhập thành công! Nhấn OK để tiếp tục tự động hoá.")

        option_xpath = f"//select[@id='ddlPhuongXa']/option[@value='{maxa}']"
        option_element = wait.until(EC.element_to_be_clickable((By.XPATH, option_xpath)))
        option_element.click()
        # 1️⃣ Chọn trạng thái "Đã kiểm tra"
        select_el = driver.find_element(By.CSS_SELECTOR, "select[name='type']")
        Select(select_el).select_by_value("3")

        # 2️⃣ Chọn trạng thái "Chưa đính kèm"
        select_file = driver.find_element(By.CSS_SELECTOR, "select[name='coFileHoSoQuet']")
        Select(select_file).select_by_value("true")
        wait = WebDriverWait(driver, 15)

        select2_span = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "/html/body/div[1]/div/div/div/div[3]/div[1]/div/div/div[2]/div/div[3]/div/div[1]/span[1]/span[1]/span/span[1]"
        )))
        select2_span.click()

        option_50 = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//li[contains(@class,'select2-results__option') and normalize-space(text())='50']"
        )))
        option_50.click()
        btn_search = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "btnSearch"))
        )

        btn_search.click()
        print("👉 Đã nhấn nút Tìm kiếm")
        wait_query_done(driver, timeout=60)
        while True:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "lstGiayChungNhan"))
            )
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#lstGiayChungNhan ul"))
            )
            uls = driver.find_elements(By.CSS_SELECTOR, "#lstGiayChungNhan ul")
            count = len(uls)
            print("👉 Số bản ghi GCN (UL):", count)
            if count == 0:
                print("🎉 Không còn bản ghi nào để duyệt. Hoàn tất!")
                break

            for i in range(count):                

                items = driver.find_elements(By.CSS_SELECTOR, "#lstGiayChungNhan ul")
                item = items[i]
                # FIX: dọn popup + overlay
                driver.execute_script("""
                    document.querySelectorAll('.modal-backdrop').forEach(e => e.remove());
                    document.querySelectorAll('div.jconfirm').forEach(e => e.remove());
                """)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", item)
                item.click()
                print(f"✔ Đã chọn bản ghi {i+1}/{count}")
                WebDriverWait(driver, 5).until(
                    lambda d: "selected" in item.get_attribute("class")
                )
                btn_duyet = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "btnDuyetDangKy"))
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_duyet)
                btn_duyet.click()
                print("👉 Đã nhấn nút Duyệt")
                if handle_optional_jconfirm(driver):
                    print("➡️ Đã xử lý popup, tiếp tục bản ghi tiếp theo")
                    continue
                btn_save = WebDriverWait(driver, 30).until(EC.element_to_be_clickable((By.ID, "btnSaveDangKy")))
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_save)
                btn_save.click()
                print("👉 Đã nhấn nút #btnSaveDangKy")
                wait_query_done(driver, timeout=60)
                handle_jconfirm_popups(driver)
                wait_query_done(driver, timeout=60)
            try:
                btn_search_again = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.ID, "btnSearch"))
                )
                btn_search_again.click()
                print("🔁 Đã nhấn lại nút Tìm kiếm để tải lô tiếp theo")
                wait_query_done(driver)
            except TimeoutException:
                print("⚠ Không bấm được nút Tìm kiếm lần nữa, dừng.")
                break
        messagebox.showinfo("Hoàn tất", "Đã duyệt xong tất cả các bản ghi.")
    except Exception as e:
        print(f"Lỗi xảy ra: {e}")
        traceback.print_exc()
        messagebox.showerror("Lỗi", f"Có lỗi xảy ra trong quá trình tự động hoá:\n{e}")
    finally:
        if driver:
            # input("Nhấn Enter để đóng trình duyệt... ")
            # driver.quit()
            pass # Keep browser open because of detach=True

# --- GUI Functions ---

def start_automation_thread(username, password, maxa, province):
    if not all([username, password, maxa, province]):
        messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập đầy đủ thông tin.")
        return

    # Chọn URL theo tỉnh
    if province == "Phú Yên":
        base_url = "https://phy.mplis.gov.vn/dc/ThuThapThongTin"
    else: # Mặc định là Đắk Lắk
        base_url = "https://dla.mplis.gov.vn/dc/ThuThapThongTin"

    # Chạy automation trong một thread riêng để không làm treo GUI
    automation_thread = threading.Thread(
        target=run_automation,
        args=(username, password, maxa, base_url),
        daemon=True
    )
    automation_thread.start()

def create_gui():
    root = tk.Tk()
    root.title("Tool Tự Động Duyệt Vận Hành")

    frame = ttk.Frame(root, padding="20")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    # Province Selection
    ttk.Label(frame, text="Chọn tỉnh:").grid(column=0, row=0, sticky=tk.W, pady=5)
    province_var = tk.StringVar()
    province_combo = ttk.Combobox(frame, textvariable=province_var)
    province_combo['values'] = ('Phú Yên', 'Đắk Lắk')
    province_combo.grid(column=1, row=0, sticky=(tk.W, tk.E))
    province_combo.set('Phú Yên') # Default value

    # Username
    ttk.Label(frame, text="Username:").grid(column=0, row=1, sticky=tk.W, pady=5)
    username_entry = ttk.Entry(frame, width=30)
    username_entry.grid(column=1, row=1, sticky=(tk.W, tk.E))
    username_entry.insert(0, "") # Default value

    # Password
    ttk.Label(frame, text="Password:").grid(column=0, row=2, sticky=tk.W, pady=5)
    password_entry = ttk.Entry(frame, show="*", width=30)
    password_entry.grid(column=1, row=2, sticky=(tk.W, tk.E))
    password_entry.insert(0, "") # Default value

    # MaXa
    ttk.Label(frame, text="Mã xã:").grid(column=0, row=3, sticky=tk.W, pady=5)
    maxa_entry = ttk.Entry(frame, width=30)
    maxa_entry.grid(column=1, row=3, sticky=(tk.W, tk.E))
    maxa_entry.insert(0, "") # Default value

    # Start Button
    start_button = ttk.Button(
        frame,
        text="Bắt đầu",
        command=lambda: start_automation_thread(
            username_entry.get(),
            password_entry.get(),
            maxa_entry.get(),
            province_var.get()
        )
    )
    start_button.grid(column=0, row=4, columnspan=2, pady=20)

    # Configure resizing
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    root.mainloop()

if __name__ == "__main__":
    create_gui()