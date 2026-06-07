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

def handle_popup_thua_dat_ton_tai(driver, timeout=5):
    try:
        popup = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"
            ))
        )

        message = popup.find_element(
            By.CSS_SELECTOR,
            "div.thuthapthongtin-message"
        ).text.strip()

        # Lấy tất cả dạng 120(31), 3000(102), 59(103)...
        ds_thua = re.findall(r"(\d+)\((\d+)\)", message)

        print(f"⚠ Popup: {message}")
        print(f"👉 Danh sách thửa cần xử lý: {ds_thua}")

        btn_ok = popup.find_element(
            By.XPATH,
            ".//div[contains(@class,'jconfirm-buttons')]//button[contains(normalize-space(.),'Đồng ý')]"
        )
        driver.execute_script("arguments[0].click();", btn_ok)

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located((
                By.CSS_SELECTOR,
                "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"
            ))
        )

        return True, ds_thua, message

    except TimeoutException:
        return False, [], None
    
def handle_confirm_delete_popup(driver, timeout=5):
    """
    Nếu sau khi bấm xóa có popup xác nhận thì bấm Đồng ý/OK/Có.
    """
    try:
        popup = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"
            ))
        )

        btn_ok = popup.find_element(
            By.XPATH,
            ".//div[contains(@class,'jconfirm-buttons')]//button["
            "contains(normalize-space(.),'Đồng ý') "
            "or contains(normalize-space(.),'OK') "
            "or contains(normalize-space(.),'Có')"
            "]"
        )

        driver.execute_script("arguments[0].click();", btn_ok)
        print("✅ Đã xác nhận popup xóa")

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located((
                By.CSS_SELECTOR,
                "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"
            ))
        )

        return True

    except TimeoutException:
        return False
    
def chon_thua_dat_trung_trong_modal(driver, modal, so_thua, so_to, timeout=20):
    """
    Tìm đúng form.item-duplicate.expanded có div.string-wrapper chứa số thửa/số tờ,
    rồi click cho đến khi form có class item-selected.
    """

    wait = WebDriverWait(driver, timeout)

    frm_thua_dat = wait.until(
        lambda d: modal.find_element(
            By.CSS_SELECTOR,
            "form[id^='frmThuaDat-']"
        )
    )

    item_forms = frm_thua_dat.find_elements(
        By.CSS_SELECTOR,
        "form.item-duplicate.expanded"
    )

    if not item_forms:
        raise Exception("Không tìm thấy form.item-duplicate.expanded trong form thửa đất")

    target_form = None

    for item in item_forms:
        try:
            string_wrapper = item.find_element(By.CSS_SELECTOR, "div.string-wrapper")
            text = " ".join(string_wrapper.text.split())

            co_so_thua = (
                f"Số thứ tự thửa: {so_thua}" in text
                or f"Số thứ tự thửa : {so_thua}" in text
            )

            co_so_to = (
                f"Số hiệu tờ bản đồ: {so_to}" in text
                or f"Số hiệu tờ bản đồ : {so_to}" in text
            )

            if co_so_thua and co_so_to:
                target_form = item
                break

        except Exception:
            continue

    if target_form is None:
        raise Exception(f"Không tìm thấy form thửa {so_thua}({so_to})")

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_form)

    for _ in range(5):
        driver.execute_script("arguments[0].click();", target_form)
        time.sleep(0.25)

        class_name = target_form.get_attribute("class") or ""

        if "item-selected" in class_name:
            print(f"✅ Đã chọn thửa {so_thua}({so_to})")
            return target_form

    raise Exception(f"Đã click nhưng thửa {so_thua}({so_to}) chưa có class item-selected")

def xoa_thua_dat_trung_trong_modal(driver, modal, so_thua, so_to, timeout=20):
    """
    Chọn đúng thửa trùng rồi bấm nút xóa trong form thửa đó.
    """

    target_form = chon_thua_dat_trung_trong_modal(
        driver,
        modal,
        so_thua,
        so_to,
        timeout=timeout
    )

    try:
        btn_delete = WebDriverWait(driver, 5).until(
            lambda d: target_form.find_element(
                By.CSS_SELECTOR,
                "div.form-wrapper div.group-action a.button-action.btnDelete"
            )
        )

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_delete)
        driver.execute_script("arguments[0].click();", btn_delete)

        print(f"🗑 Đã bấm nút xóa thửa {so_thua}({so_to})")

    except Exception:
        # Phương án dự phòng: Ctrl + Delete
        print(f"⚠ Không bấm được nút xóa, thử Ctrl + Delete cho thửa {so_thua}({so_to})")

        target_form.click()
        webdriver.ActionChains(driver)\
            .key_down(Keys.CONTROL)\
            .send_keys(Keys.DELETE)\
            .key_up(Keys.CONTROL)\
            .perform()

    handle_confirm_delete_popup(driver)

    # Chờ form thửa vừa xóa biến mất hoặc không còn selected
    time.sleep(0.5)

    return True

def xoa_tat_ca_thua_trung_va_luu(driver, ds_thua, timeout=20):
    """
    Mở modal từ UL đang selected, xóa tất cả thửa trong ds_thua,
    sau đó bấm nút Lưu trong #vModuleThuThapThongTinChiTiet.
    """

    wait = WebDriverWait(driver, timeout)

    # UL GCN đang selected
    ul_selected = wait.until(
        EC.presence_of_element_located((
            By.CSS_SELECTOR,
            "#lstGiayChungNhan ul.vbd-search-item.thuthapthongtin-item.selected"
        ))
    )

    # Bấm nút Chỉnh sửa
    btn_edit = ul_selected.find_element(By.CSS_SELECTOR, "a.btnEdit")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_edit)
    driver.execute_script("arguments[0].click();", btn_edit)

    print("👉 Đã bấm Chỉnh sửa GCN đang chọn")

    # Chờ modal mở
    modal = wait.until(
        EC.visibility_of_element_located((
            By.CSS_SELECTOR,
            "div[id^='mdlThuThapThongTinChiTiet-'].modal.show, "
            "div[id^='mdlThuThapThongTinChiTiet-'].in"
        ))
    )

    print("✅ Modal thu thập thông tin chi tiết đã mở")

    # Xóa từng thửa trong ds_thua
    for so_thua, so_to in ds_thua:
        print(f"👉 Đang xử lý xóa thửa {so_thua}({so_to})")
        xoa_thua_dat_trung_trong_modal(driver, modal, so_thua, so_to, timeout=timeout)

    # Bấm Lưu
    btn_save = wait.until(
        EC.element_to_be_clickable((
            By.CSS_SELECTOR,
            "#vModuleThuThapThongTinChiTiet button[id^='btnSave-'], "
            "#vModuleThuThapThongTinChiTiet a[id^='btnSave-']"
        ))
    )

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_save)
    driver.execute_script("arguments[0].click();", btn_save)

    print("💾 Đã bấm nút Lưu sau khi xóa tất cả thửa trùng")

    wait_query_done(driver, timeout=60)
    handle_confirm_delete_popup(driver)

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
        # Nhập mã hồ sơ vào ô Số phát hành trong vùng tra cứu
        # Nhập mã GCN vào ô Số phát hành
        input_mahs = wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR,
            "#wpThongTinTraCuu input[name='soPhatHanh']"
        )))

        input_mahs.clear()
        input_mahs.send_keys(ma_GCN)

        print(f"👉 Đã nhập mã GCN: {ma_GCN}")
        btn_search = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "btnSearch"))
        )

        btn_search.click()
        print("👉 Đã nhấn nút Tìm kiếm")
        wait_query_done(driver, timeout=60)

        # Chờ vùng kết quả
        wp_ketqua = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "wpKetQuaTraCuu"))
        )

        # Tìm danh sách GCN trong vùng kết quả
        lst_gcn = WebDriverWait(wp_ketqua, 15).until(
            lambda e: e.find_element(By.ID, "lstGiayChungNhan")
        )

        uls = lst_gcn.find_elements(
            By.CSS_SELECTOR,
            "ul.vbd-search-item.list-group.thuthapthongtin-item"
        )

        if not uls:
            print(f"⚠ Không tìm thấy GCN: {ma_GCN}")
            # chuyển sang GCN tiếp theo
            continue

        # Vì đã tìm theo ma_GCN nên thường chỉ lấy bản ghi đầu tiên
        ul = uls[0]

        # Kiểm tra icon đã duyệt màu xanh
        checked_icons = ul.find_elements(
            By.CSS_SELECTOR,
            "span.icon i.fa-check-circle.green"
        )

        if checked_icons:
            print(f"✅ GCN {ma_GCN} đã có dấu xanh, bỏ qua")
            continue

        # Nếu chưa có dấu xanh thì chọn UL
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", ul)
        driver.execute_script("arguments[0].click();", ul)

        WebDriverWait(driver, 10).until(
            lambda d: "selected" in ul.get_attribute("class")
        )

        print(f"✔ Đã chọn GCN chưa duyệt: {ma_GCN}")
        # Sau khi chọn UL thành selected
        btn_kiemtra = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.CSS_SELECTOR,
                "#wpThongTinChiTiet #btnKiemTraDangKy"
            ))
        )

        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_kiemtra)
        driver.execute_script("arguments[0].click();", btn_kiemtra)

        print(f"👉 Đã nhấn nút Kiểm tra đăng ký cho GCN: {ma_GCN}")
        co_popup, ds_thua, message = handle_popup_thua_dat_ton_tai(driver)

        if co_popup and ds_thua:
            print(f"⚠ Có {len(ds_thua)} thửa đã tồn tại, tiến hành xóa trong modal")

            xoa_tat_ca_thua_trung_va_luu(driver, ds_thua)

            # Sau khi lưu xong, bấm kiểm tra lại
            btn_kiemtra = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "#wpThongTinChiTiet #btnKiemTraDangKy"
                ))
            )
            driver.execute_script("arguments[0].click();", btn_kiemtra)

            print(f"🔁 Đã kiểm tra lại GCN {ma_GCN} sau khi xóa thửa trùng")
            
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