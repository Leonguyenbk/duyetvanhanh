import time
import traceback
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk, messagebox

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


# ============================================================
# 1. CẤU HÌNH CHUNG
#    Sau này đổi link, tỉnh, trạng thái, số dòng/trang thì sửa ở đây.
# ============================================================

PROVINCE_URLS = {
    "Phú Yên": "https://phy.mplis.gov.vn/dc/ThuThapThongTin",
    "Đắk Lắk": "https://dla.mplis.gov.vn/dc/ThuThapThongTin",
}

DEFAULT_PROVINCE = "Phú Yên"

@dataclass
class AppConfig:
    province: str
    username: str
    password: str
    maxa: str
    base_url: str
    status_type: str = "3"             # 3 = Đã kiểm tra
    has_scan_file: str = "true"        # true = Chưa đính kèm theo logic hiện tại của web
    page_size: str = "50"
    timeout: int = 20
    detach_browser: bool = True


# ============================================================
# 2. SELECTOR / XPATH TẬP TRUNG
#    Sau này web đổi id/class/xpath thì chỉ sửa tại khối này.
# ============================================================

class Sel:
    USERNAME = (By.NAME, "username")
    PASSWORD = (By.NAME, "password")

    DDL_PHUONG_XA_OPTION_XPATH = "//select[@id='ddlPhuongXa']/option[@value='{maxa}']"

    SELECT_TYPE = (By.CSS_SELECTOR, "select[name='type']")
    SELECT_SCAN_FILE = (By.CSS_SELECTOR, "select[name='coFileHoSoQuet']")

    # Select2 chọn số dòng/trang
    PAGE_SIZE_SELECT2 = (
        By.XPATH,
        "/html/body/div[1]/div/div/div/div[3]/div[1]/div/div/div[2]/div/div[3]/div/div[1]/span[1]/span[1]/span/span[1]"
    )
    PAGE_SIZE_OPTION_XPATH = "//li[contains(@class,'select2-results__option') and normalize-space(text())='{page_size}']"

    BTN_SEARCH = (By.ID, "btnSearch")
    LIST_GCN = (By.ID, "lstGiayChungNhan")
    LIST_GCN_ITEMS = (By.CSS_SELECTOR, "#lstGiayChungNhan ul")

    BTN_DUYET_DANG_KY = (By.ID, "btnDuyetDangKy")
    BTN_SAVE_DANG_KY = (By.ID, "btnSaveDangKy")

    LOADING_MASK = (By.CSS_SELECTOR, "div.jquery-loading-modal_bg")

    JCONFIRM_POPUP_CSS = "body > div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"
    JCONFIRM_POPUP = (By.CSS_SELECTOR, JCONFIRM_POPUP_CSS)
    JCONFIRM_BUTTONS = (By.CSS_SELECTOR, JCONFIRM_POPUP_CSS + " div.jconfirm-buttons > button")
    JCONFIRM_ORANGE_BUTTON = (
        By.CSS_SELECTOR,
        JCONFIRM_POPUP_CSS + " div.jconfirm-buttons > button.btn.btn-orange"
    )

    DANGKY_MODAL_CSS = "div.modal.modal-fullscreen[id^='mdlDangKyWizard-']"
    DANGKY_MODAL = (By.CSS_SELECTOR, DANGKY_MODAL_CSS)
    DANGKY_MODAL_CLOSE = (By.CSS_SELECTOR, DANGKY_MODAL_CSS + " div.modal-header > button.close")


# ============================================================
# 3. HÀM TIỆN ÍCH SELENIUM
#    Gồm chờ tải, click an toàn, dọn overlay/modal rác.
# ============================================================

def create_driver(detach=True):
    options = Options()
    options.add_argument("--start-maximized")
    options.add_experimental_option("detach", detach)
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def wait_visible(driver, locator, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located(locator)
    )


def wait_clickable(driver, locator, timeout=20):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable(locator)
    )


def safe_click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def cleanup_overlays(driver):
    """Dọn các lớp che còn sót gây block click."""
    try:
        driver.execute_script("""
            document.querySelectorAll('.modal-backdrop').forEach(e => e.remove());
            document.querySelectorAll('div.jconfirm').forEach(e => e.remove());
            document.querySelectorAll('div.jquery-loading-modal_bg').forEach(e => e.remove());
        """)
    except Exception:
        pass


def wait_loading_mask(driver, timeout=10):
    """Chờ loading mask biến mất, sau đó dọn mask còn sót."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located(Sel.LOADING_MASK)
        )
    except Exception:
        pass

    try:
        driver.execute_script("""
            document.querySelectorAll('div.jquery-loading-modal_bg')
                    .forEach(e => e.remove());
        """)
    except Exception:
        pass


def wait_query_done(driver, timeout=60, ajax_wait=5):
    """Chờ AJAX + loading mask hoàn tất."""
    end_time = time.time() + timeout

    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.jQuery !== undefined;")
        )
    except Exception:
        wait_loading_mask(driver)
        return

    phase1_end = time.time() + ajax_wait
    saw_ajax = False

    while time.time() < phase1_end:
        try:
            active = driver.execute_script("return jQuery.active;")
            if active > 0:
                saw_ajax = True
                break
        except Exception:
            break
        time.sleep(0.1)

    if not saw_ajax:
        wait_loading_mask(driver)
        return

    while time.time() < end_time:
        try:
            active = driver.execute_script("return jQuery.active;")
            if active == 0:
                break
        except Exception:
            break
        time.sleep(0.1)

    wait_loading_mask(driver)


# ============================================================
# 4. KHỐI XỬ LÝ POPUP / MODAL
#    Nếu sau này popup đổi nút, đổi class thì sửa ở đây.
# ============================================================

def close_dangky_modal(driver, timeout=10):
    try:
        modal = wait_visible(driver, Sel.DANGKY_MODAL, timeout)
        if not modal.is_displayed():
            return False

        close_btn = wait_clickable(driver, Sel.DANGKY_MODAL_CLOSE, timeout)
        safe_click(driver, close_btn)

        WebDriverWait(driver, timeout).until(
            EC.invisibility_of_element_located(Sel.DANGKY_MODAL)
        )
        print("🔒 Đã đóng modal DangKyWizard")
        return True
    except Exception:
        return False


def handle_optional_jconfirm(driver, timeout=10):
    """Popup có thể xuất hiện khi chọn/duyệt bản ghi."""
    try:
        wait_visible(driver, Sel.JCONFIRM_POPUP, timeout)
    except Exception:
        return False

    print("⚠️ Xuất hiện popup jConfirm tùy chọn")
    try:
        btn_ok = wait_clickable(driver, Sel.JCONFIRM_BUTTONS, 5)
        safe_click(driver, btn_ok)

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located(Sel.JCONFIRM_POPUP)
        )
        print("✅ Đã xử lý popup tùy chọn")
        return True
    except Exception as e:
        print(f"❌ Không xử lý được popup tùy chọn: {e}")
        return False


def handle_save_jconfirm_popups(driver, timeout_first=20, timeout_second=5):
    """
    Sau khi bấm lưu:
    - Popup 1: bấm nút cam.
    - Popup 2 nếu có: bấm nút bất kỳ/Đồng ý.
    - Đóng Wizard nếu còn mở.
    """
    try:
        wait_visible(driver, Sel.JCONFIRM_POPUP, timeout_first)
    except Exception:
        return False

    print("✅ Popup jConfirm sau lưu đã xuất hiện")

    try:
        btn_cam = wait_clickable(driver, Sel.JCONFIRM_ORANGE_BUTTON, 10)
        safe_click(driver, btn_cam)

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located(Sel.JCONFIRM_POPUP)
        )
        print("👉 Đã bấm nút cam popup đầu tiên")
    except Exception as e:
        print(f"❌ Không xử lý được popup đầu tiên: {e}")
        return False

    try:
        wait_visible(driver, Sel.JCONFIRM_POPUP, timeout_second)
        print("⚠️ Có popup thứ hai")

        btn_ok2 = wait_clickable(driver, Sel.JCONFIRM_BUTTONS, 10)
        safe_click(driver, btn_ok2)

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located(Sel.JCONFIRM_POPUP)
        )
        print("👉 Đã bấm Đồng ý popup thứ hai")
    except Exception:
        print("ℹ️ Không có popup thứ hai")

    close_dangky_modal(driver)
    return True


# ============================================================
# 5. KHỐI THAO TÁC NGHIỆP VỤ TRÊN WEB
#    Mỗi bước nghiệp vụ là một hàm riêng.
# ============================================================

def login(driver, cfg: AppConfig):
    driver.get(cfg.base_url)

    wait_clickable(driver, Sel.USERNAME, cfg.timeout).send_keys(cfg.username)
    pwd = wait_clickable(driver, Sel.PASSWORD, cfg.timeout)
    pwd.send_keys(cfg.password)
    pwd.send_keys(Keys.ENTER)

    print("✅ Đã gửi thông tin đăng nhập")


def select_commune(driver, cfg: AppConfig):
    option_xpath = Sel.DDL_PHUONG_XA_OPTION_XPATH.format(maxa=cfg.maxa)
    option = wait_clickable(driver, (By.XPATH, option_xpath), cfg.timeout)
    safe_click(driver, option)
    print(f"✅ Đã chọn mã xã: {cfg.maxa}")


def apply_filters(driver, cfg: AppConfig):
    Select(wait_visible(driver, Sel.SELECT_TYPE, cfg.timeout)).select_by_value(cfg.status_type)
    print(f"✅ Đã chọn trạng thái type={cfg.status_type}")

    Select(wait_visible(driver, Sel.SELECT_SCAN_FILE, cfg.timeout)).select_by_value(cfg.has_scan_file)
    print(f"✅ Đã chọn coFileHoSoQuet={cfg.has_scan_file}")

    page_size_span = wait_clickable(driver, Sel.PAGE_SIZE_SELECT2, 15)
    safe_click(driver, page_size_span)

    option_xpath = Sel.PAGE_SIZE_OPTION_XPATH.format(page_size=cfg.page_size)
    page_size_option = wait_clickable(driver, (By.XPATH, option_xpath), 15)
    safe_click(driver, page_size_option)
    print(f"✅ Đã chọn số dòng/trang: {cfg.page_size}")


def search_records(driver):
    btn_search = wait_clickable(driver, Sel.BTN_SEARCH, 10)
    safe_click(driver, btn_search)
    print("👉 Đã nhấn nút Tìm kiếm")
    wait_query_done(driver, timeout=60)


def get_record_items(driver):
    wait_visible(driver, Sel.LIST_GCN, 10)
    return driver.find_elements(*Sel.LIST_GCN_ITEMS)


def select_record_by_index(driver, index):
    items = get_record_items(driver)

    if index >= len(items):
        return False

    item = items[index]
    cleanup_overlays(driver)
    safe_click(driver, item)

    WebDriverWait(driver, 5).until(
        lambda d: "selected" in item.get_attribute("class")
    )
    print(f"✔ Đã chọn bản ghi {index + 1}/{len(items)}")
    return True


def click_duyet(driver):
    btn_duyet = wait_clickable(driver, Sel.BTN_DUYET_DANG_KY, 10)
    safe_click(driver, btn_duyet)
    print("👉 Đã nhấn nút Duyệt")


def click_save(driver):
    btn_save = wait_clickable(driver, Sel.BTN_SAVE_DANG_KY, 30)
    safe_click(driver, btn_save)
    print("👉 Đã nhấn nút Lưu/Duyệt đăng ký")
    wait_query_done(driver, timeout=60)


def process_one_record(driver, index):
    """
    Xử lý 01 bản ghi.
    Sau này đổi thao tác từng bản ghi thì sửa hàm này là chính.
    """
    if not select_record_by_index(driver, index):
        return False

    click_duyet(driver)

    if handle_optional_jconfirm(driver):
        print("➡️ Có popup khi duyệt, bỏ qua bản ghi này và tiếp tục")
        return True

    click_save(driver)
    handle_save_jconfirm_popups(driver)
    wait_query_done(driver, timeout=60)
    return True


def process_all_records(driver):
    """
    Vòng lặp chính:
    - Lấy danh sách bản ghi trên trang.
    - Xử lý từng bản ghi.
    - Tìm kiếm lại để tải lô tiếp theo.
    """
    while True:
        items = get_record_items(driver)
        count = len(items)
        print("👉 Số bản ghi GCN:", count)

        if count == 0:
            print("🎉 Không còn bản ghi nào để duyệt. Hoàn tất!")
            break

        for index in range(count):
            try:
                process_one_record(driver, index)
            except Exception as e:
                print(f"⚠️ Lỗi tại bản ghi {index + 1}/{count}: {e}")
                traceback.print_exc()
                cleanup_overlays(driver)
                continue

        try:
            search_records(driver)
            print("🔁 Đã tìm kiếm lại để tải lô tiếp theo")
        except TimeoutException:
            print("⚠️ Không bấm được nút Tìm kiếm lần nữa, dừng.")
            break


# ============================================================
# 6. KHỐI CHẠY AUTOMATION
# ============================================================

def run_automation(cfg: AppConfig):
    driver = None
    try:
        driver = create_driver(detach=cfg.detach_browser)

        login(driver, cfg)

        messagebox.showinfo(
            "Info",
            "Đăng nhập thành công! Nhấn OK để tiếp tục tự động hoá."
        )

        select_commune(driver, cfg)
        apply_filters(driver, cfg)
        search_records(driver)
        process_all_records(driver)

        messagebox.showinfo("Hoàn tất", "Đã duyệt xong tất cả các bản ghi.")

    except Exception as e:
        print(f"Lỗi xảy ra: {e}")
        traceback.print_exc()
        messagebox.showerror(
            "Lỗi",
            f"Có lỗi xảy ra trong quá trình tự động hoá:\n{e}"
        )
    finally:
        # Giữ trình duyệt mở do detach=True
        pass


# ============================================================
# 7. GUI
# ============================================================

def build_config_from_gui(username, password, maxa, province):
    if province not in PROVINCE_URLS:
        raise ValueError(f"Tỉnh chưa được cấu hình link: {province}")

    return AppConfig(
        province=province,
        username=username.strip(),
        password=password,
        maxa=maxa.strip(),
        base_url=PROVINCE_URLS[province],
    )


def start_automation_thread(username, password, maxa, province):
    if not all([username, password, maxa, province]):
        messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập đầy đủ thông tin.")
        return

    try:
        cfg = build_config_from_gui(username, password, maxa, province)
    except Exception as e:
        messagebox.showerror("Lỗi cấu hình", str(e))
        return

    thread = threading.Thread(
        target=run_automation,
        args=(cfg,),
        daemon=True
    )
    thread.start()


def create_gui():
    root = tk.Tk()
    root.title("Tool Tự Động Duyệt Vận Hành - Bản chia khối")

    frame = ttk.Frame(root, padding="20")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    ttk.Label(frame, text="Chọn tỉnh:").grid(column=0, row=0, sticky=tk.W, pady=5)
    province_var = tk.StringVar(value=DEFAULT_PROVINCE)
    province_combo = ttk.Combobox(
        frame,
        textvariable=province_var,
        values=list(PROVINCE_URLS.keys()),
        state="readonly"
    )
    province_combo.grid(column=1, row=0, sticky=(tk.W, tk.E))

    ttk.Label(frame, text="Username:").grid(column=0, row=1, sticky=tk.W, pady=5)
    username_entry = ttk.Entry(frame, width=30)
    username_entry.grid(column=1, row=1, sticky=(tk.W, tk.E))

    ttk.Label(frame, text="Password:").grid(column=0, row=2, sticky=tk.W, pady=5)
    password_entry = ttk.Entry(frame, show="*", width=30)
    password_entry.grid(column=1, row=2, sticky=(tk.W, tk.E))

    ttk.Label(frame, text="Mã xã:").grid(column=0, row=3, sticky=tk.W, pady=5)
    maxa_entry = ttk.Entry(frame, width=30)
    maxa_entry.grid(column=1, row=3, sticky=(tk.W, tk.E))

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

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    root.mainloop()


if __name__ == "__main__":
    create_gui()
