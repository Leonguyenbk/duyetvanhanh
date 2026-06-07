import time
import traceback
import threading
import re
import os
import csv
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


BASE_URL = "https://dla.mplis.gov.vn/dc/ThuThapThongTin"


# =========================================================
# LOGIN
# =========================================================

def get_login_fields(wait):
    username_box = wait.until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                "input[autocomplete='username'], input[name='username']",
            )
        )
    )

    password_box = wait.until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                "input[autocomplete='current-password'], input[name='password']",
            )
        )
    )

    return username_box, password_box


# =========================================================
# WAIT AJAX / LOADING
# =========================================================

def wait_query_done(driver, timeout=30, ajax_wait=5):
    def wait_loading_mask(driver, timeout=10):
        try:
            WebDriverWait(driver, timeout).until(
                EC.invisibility_of_element_located(
                    (By.CSS_SELECTOR, "div.jquery-loading-modal_bg")
                )
            )
        except:
            pass

        try:
            driver.execute_script("""
                document.querySelectorAll('div.jquery-loading-modal_bg')
                        .forEach(e => e.remove());
            """)
        except:
            pass

    end_time = time.time() + timeout

    try:
        WebDriverWait(driver, 5).until(
            lambda d: d.execute_script("return window.jQuery !== undefined;")
        )
    except:
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
        except:
            break

    if not saw_ajax:
        wait_loading_mask(driver)
        return

    while time.time() < end_time:
        try:
            active = driver.execute_script("return jQuery.active;")
            if active == 0:
                break
        except:
            break

    wait_loading_mask(driver)


def find_visible_element(driver, css_selector, timeout=20):
    wait = WebDriverWait(driver, timeout)

    def _find(d):
        elements = d.find_elements(By.CSS_SELECTOR, css_selector)

        for el in elements:
            try:
                if el.is_displayed():
                    return el
            except:
                pass

        return False

    return wait.until(_find)


# =========================================================
# FILE PDF -> MÃ GCN
# =========================================================

def lay_ma_gcn_tu_ten_file(filename):
    name = os.path.splitext(filename)[0].strip()
    name = re.sub(r"(?i)-GT$", "", name).strip()
    return name


def lay_danh_sach_gcn_tu_folder(folder_path):
    files = []

    for f in os.listdir(folder_path):
        if f.lower().endswith(".pdf"):
            ma_gcn = lay_ma_gcn_tu_ten_file(f)
            files.append((f, ma_gcn))

    files.sort(key=lambda x: x[0].lower())
    return files


# =========================================================
# CSV KẾT QUẢ
# =========================================================

def tao_file_ket_qua(folder_path):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(folder_path, f"ket_qua_duyet_van_hanh_{now}.csv")


def ghi_ket_qua(csv_path, row):
    file_exists = os.path.exists(csv_path)

    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "STT",
                "TenFile",
                "MaGCN",
                "TrangThai",
                "ThuaDaXoa",
                "GhiChu",
                "ThoiGian",
            ],
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


# =========================================================
# POPUP
# =========================================================

def handle_jconfirm_popups(driver, timeout_first=20, timeout_second=5):
    POPUP_CSS = "body > div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"

    try:
        WebDriverWait(driver, timeout_first).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
        )
    except TimeoutException:
        return False

    print("✅ Popup jConfirm xuất hiện")

    try:
        btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    POPUP_CSS + " div.jconfirm-buttons > button",
                )
            )
        )

        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        driver.execute_script("arguments[0].click();", btn)

        print("👉 Đã nhấn nút xác nhận popup đầu tiên")

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
        )

    except Exception as e:
        print(f"⚠ Không xử lý được popup đầu tiên: {e}")

    try:
        WebDriverWait(driver, timeout_second).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
        )

        btn2 = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable(
                (
                    By.CSS_SELECTOR,
                    POPUP_CSS + " div.jconfirm-buttons > button",
                )
            )
        )

        driver.execute_script("arguments[0].click();", btn2)

        print("👉 Đã nhấn popup thứ hai")

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
        )

    except TimeoutException:
        pass
    except Exception as e:
        print(f"⚠ Không xử lý được popup thứ hai: {e}")

    return True


def handle_confirm_delete_popup(driver, timeout=5):
    try:
        popup = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open",
                )
            )
        )

        btn_ok = popup.find_element(
            By.XPATH,
            ".//div[contains(@class,'jconfirm-buttons')]//button["
            "contains(normalize-space(.),'Đồng ý') "
            "or contains(normalize-space(.),'OK') "
            "or contains(normalize-space(.),'Có') "
            "or contains(@class,'btn-orange') "
            "or contains(@class,'btn-red')"
            "]",
        )

        driver.execute_script("arguments[0].click();", btn_ok)

        print("✅ Đã xác nhận popup xóa")

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open",
                )
            )
        )

        return True

    except TimeoutException:
        print("ℹ Không thấy popup xác nhận xóa")
        return False

    except Exception as e:
        print(f"⚠ Lỗi xử lý popup xóa: {e}")
        return False


def handle_popup_orange_after_save_dangky(driver, timeout=8):
    POPUP_CSS = "body > div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"
    BTN_ORANGE_CSS = (
        "body > div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open "
        "div.jconfirm-buttons > button.btn.btn-orange"
    )

    end_time = time.time() + timeout

    while time.time() < end_time:
        try:
            btn_orange = driver.find_element(By.CSS_SELECTOR, BTN_ORANGE_CSS)

            if btn_orange.is_displayed() and btn_orange.is_enabled():
                driver.execute_script("arguments[0].click();", btn_orange)

                print("✅ Đã nhấn nhanh nút cam xác nhận sau #btnSaveDangKy")

                try:
                    WebDriverWait(driver, 5).until(
                        EC.invisibility_of_element_located((By.CSS_SELECTOR, POPUP_CSS))
                    )
                except:
                    pass

                return True

        except:
            pass

    print("ℹ Không thấy popup nút cam sau #btnSaveDangKy")
    return False


# =========================================================
# POPUP THỬA ĐẤT TỒN TẠI
# =========================================================

def handle_popup_thua_dat_ton_tai(driver, timeout=1):
    try:
        popup = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open",
                )
            )
        )

        try:
            message = popup.find_element(
                By.CSS_SELECTOR,
                "div.thuthapthongtin-message",
            ).text.strip()
        except:
            message = popup.text.strip()

        ds_thua = re.findall(r"(\d+)\((\d+)\)", message)

        print(f"⚠ Popup: {message}")
        print(f"👉 Danh sách thửa cần xử lý (số_thứ_tự, số_tờ): {ds_thua}")

        btn_ok = popup.find_element(
            By.XPATH,
            ".//div[contains(@class,'jconfirm-buttons')]//button["
            "contains(normalize-space(.),'Đồng ý') "
            "or contains(normalize-space(.),'OK') "
            "or contains(normalize-space(.),'Có')"
            "]",
        )

        driver.execute_script("arguments[0].click();", btn_ok)

        WebDriverWait(driver, 10).until(
            EC.invisibility_of_element_located(
                (
                    By.CSS_SELECTOR,
                    "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open",
                )
            )
        )

        return True, ds_thua, message

    except TimeoutException:
        return False, [], None
    except Exception as e:
        print(f"⚠ Lỗi đọc popup thửa tồn tại: {e}")
        return False, [], None


# =========================================================
# ACTIVE MODULE / FORM THỬA ĐẤT
# =========================================================

def tim_modal_thu_thap_chi_tiet(driver, timeout=20):
    return find_visible_element(
        driver,
        "div[id^='mdlThuThapThongTinChiTiet-']",
        timeout=timeout,
    )


def get_active_thuthap_module(driver, timeout=20):
    wait = WebDriverWait(driver, timeout)

    def _find(d):
        selectors = [
            "#vModuleThuThapThongTinChiTiet",
            "div[id^='vModuleThuThapThongTinChiTiet']",
        ]

        for css in selectors:
            els = d.find_elements(By.CSS_SELECTOR, css)
            for el in els:
                try:
                    if el.is_displayed():
                        return el
                except:
                    pass

        return False

    return wait.until(_find)


def get_active_frm_thua_dat(driver, timeout=20):
    wait = WebDriverWait(driver, timeout)

    module = get_active_thuthap_module(driver, timeout=timeout)

    def _find(d):
        fieldsets = module.find_elements(
            By.CSS_SELECTOR, "div[id^='frmThuaDat-']"
        )

        for fieldset in fieldsets:
            try:
                if fieldset.is_displayed():
                    return fieldset
            except:
                pass

        return False

    frm_thua_dat = wait.until(_find)

    print("✅ Đã tìm thấy div[id^='frmThuaDat-'] đang active")

    return frm_thua_dat

def scroll_deep_to_bottom(driver, root):
    """
    Cuộn root và toàn bộ div con có scrollbar xuống đáy.
    Dùng cho #vModuleThuThapThongTinChiTiet.
    """
    driver.execute_script("""
        const root = arguments[0];

        function scrollOne(el) {
            try {
                if (el.scrollHeight > el.clientHeight) {
                    el.scrollTop = el.scrollHeight;
                }
            } catch(e) {}
        }

        scrollOne(root);

        const all = root.querySelectorAll('*');
        all.forEach(el => scrollOne(el));

        try {
            root.scrollIntoView({block: 'end', inline: 'nearest'});
        } catch(e) {}
    """, root)


def bam_nut_luu_thu_thap_chi_tiet(driver, timeout=20):
    """
    Tìm và bấm nút Lưu dạng #btnSave-* trong #vModuleThuThapThongTinChiTiet.
    Có cuộn xuống đáy và nhiều cách bấm dự phòng.
    """

    wait = WebDriverWait(driver, timeout)

    module = get_active_thuthap_module(driver, timeout=timeout)

    # Cuộn xuống đáy nhiều lần vì modal có thể có scroll lồng nhau
    for _ in range(8):
        scroll_deep_to_bottom(driver, module)

    btn_save = None

    selectors = [
        "#vModuleThuThapThongTinChiTiet button[id^='btnSave-']",
        "#vModuleThuThapThongTinChiTiet a[id^='btnSave-']",
        "button[id^='btnSave-']",
        "a[id^='btnSave-']",
        "#btnSave-afd9676c-6964-4386-8b40-9a9ae7d8490a",
    ]

    for css in selectors:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, css)

            for btn in buttons:
                try:
                    if btn.is_displayed():
                        btn_save = btn
                        print(f"✅ Tìm thấy nút Lưu bằng selector: {css}")
                        break
                except:
                    pass

            if btn_save:
                break

        except:
            continue

    if btn_save is None:
        raise Exception("Không tìm thấy nút Lưu #btnSave-* đang hiển thị")

    # Cuộn đúng vào nút
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        btn_save
    )

    # Dọn overlay/loading còn sót
    try:
        driver.execute_script("""
            document.querySelectorAll('div.jquery-loading-modal_bg')
                    .forEach(e => e.remove());
            document.querySelectorAll('.modal-backdrop')
                    .forEach(e => e.remove());
        """)
    except:
        pass

    # Cách 1: click thường bằng ActionChains
    try:
        ActionChains(driver).move_to_element(btn_save).pause(0.2).click().perform()
        print("💾 Đã bấm nút Lưu bằng ActionChains")
        return True
    except Exception as e:
        print(f"⚠ ActionChains click nút Lưu thất bại: {e}")

    # Cách 2: JS click
    try:
        driver.execute_script("arguments[0].click();", btn_save)
        print("💾 Đã bấm nút Lưu bằng JS click")
        return True
    except Exception as e:
        print(f"⚠ JS click nút Lưu thất bại: {e}")

    # Cách 3: trigger native MouseEvent
    try:
        driver.execute_script("""
            const btn = arguments[0];
            const evt = new MouseEvent('click', {
                bubbles: true,
                cancelable: true,
                view: window
            });
            btn.dispatchEvent(evt);
        """, btn_save)

        print("💾 Đã bấm nút Lưu bằng MouseEvent")
        return True

    except Exception as e:
        print(f"⚠ MouseEvent click nút Lưu thất bại: {e}")

    raise Exception("Không thể bấm nút Lưu #btnSave-*")


# =========================================================
# TÌM VÀ CHỌN THỬA ĐẤT CẦN XÓA
# =========================================================

def bam_nut_luu_thu_thap_chi_tiet(driver, timeout=20):
    """
    Click the save button in the active ThuThapThongTinChiTiet module.
    This override keeps the lookup scoped to the active module footer because
    deleting land parcels can re-render the module and stale/broad selectors
    may miss the real #btnSave-{vmodule-id} button.
    """
    wait = WebDriverWait(driver, timeout)

    def _find_save_button(d):
        module = get_active_thuthap_module(d, timeout=timeout)
        vmodule_id = module.get_attribute("vmodule-id")

        selectors = []
        if vmodule_id:
            selectors.append(f"#btnSave-{vmodule_id}")

        selectors.extend([
            ".panel-footer button[id^='btnSave-']",
            ".panel-footer a[id^='btnSave-']",
            "button[id^='btnSave-']",
            "a[id^='btnSave-']",
        ])

        for css in selectors:
            try:
                for btn in module.find_elements(By.CSS_SELECTOR, css):
                    disabled = btn.get_attribute("disabled")
                    aria_disabled = btn.get_attribute("aria-disabled")

                    if (
                        btn.is_displayed()
                        and btn.is_enabled()
                        and disabled is None
                        and aria_disabled != "true"
                    ):
                        print(f"✅ Tìm thấy nút Lưu bằng selector: {css}")
                        return btn
            except:
                pass

        return False

    wait_query_done(driver, timeout=25, ajax_wait=1)
    btn_save = wait.until(_find_save_button)

    for _ in range(4):
        module = get_active_thuthap_module(driver, timeout=timeout)
        scroll_deep_to_bottom(driver, module)

    btn_save = wait.until(_find_save_button)
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        btn_save,
    )
    try:
        WebDriverWait(driver, 5).until(
            EC.invisibility_of_element_located(
                (By.CSS_SELECTOR, "div.jquery-loading-modal_bg")
            )
        )
    except:
        pass

    click_errors = []

    try:
        ActionChains(driver).move_to_element(btn_save).pause(0.2).click().perform()
        print("💾 Đã bấm nút Lưu bằng ActionChains")
        return True
    except Exception as e:
        click_errors.append(f"ActionChains: {e}")
        print(f"⚠ ActionChains click nút Lưu thất bại: {e}")

    try:
        btn_save = wait.until(_find_save_button)
        driver.execute_script("arguments[0].click();", btn_save)
        print("💾 Đã bấm nút Lưu bằng JS click")
        return True
    except Exception as e:
        click_errors.append(f"JS click: {e}")
        print(f"⚠ JS click nút Lưu thất bại: {e}")

    try:
        btn_save = wait.until(_find_save_button)
        driver.execute_script("""
            const btn = arguments[0];
            btn.focus();
            btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
            btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
            btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        """, btn_save)
        print("💾 Đã bấm nút Lưu bằng MouseEvent")
        return True
    except Exception as e:
        click_errors.append(f"MouseEvent: {e}")
        print(f"⚠ MouseEvent click nút Lưu thất bại: {e}")

    raise Exception("Không thể bấm nút Lưu #btnSave-*; " + " | ".join(click_errors))


def bam_nut_luu_thu_thap_chi_tiet(driver, timeout=20):
    """
    Click the Save button in the active ThuThapThongTinChiTiet modal footer.
    The button id changes per modal, so scope to the current modal and prefer
    the green save button inside .panel-footer.
    """
    wait = WebDriverWait(driver, timeout)

    def _find_save_button(d):
        modal = tim_modal_thu_thap_chi_tiet(d, timeout=timeout)

        selectors = [
            ".panel-footer .btn.btn-green[id^='btnSave-']",
            ".panel-footer button[id^='btnSave-']",
            ".panel-footer a[id^='btnSave-']",
            "button[id^='btnSave-']",
            "a[id^='btnSave-']",
        ]

        for css in selectors:
            try:
                for btn in modal.find_elements(By.CSS_SELECTOR, css):
                    disabled = btn.get_attribute("disabled")
                    aria_disabled = btn.get_attribute("aria-disabled")

                    if (
                        btn.is_displayed()
                        and btn.is_enabled()
                        and disabled is None
                        and aria_disabled != "true"
                    ):
                        btn_id = btn.get_attribute("id")
                        print(f"✅ Tìm thấy nút Lưu {btn_id} bằng selector: {css}")
                        return btn
            except:
                pass

        return False

    wait_query_done(driver, timeout=25, ajax_wait=1)
    btn_save = wait.until(_find_save_button)

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        btn_save,
    )
    driver.execute_script(
        "arguments[0].removeAttribute('disabled'); arguments[0].style.display='inline-block'; arguments[0].style.visibility='visible';",
        btn_save,
    )

    click_errors = []

    try:
        ActionChains(driver).move_to_element(btn_save).pause(0.2).click().perform()
        print("💾 Đã bấm nút Lưu trong panel-footer bằng ActionChains")
        return True
    except Exception as e:
        click_errors.append(f"ActionChains: {e}")
        print(f"⚠ ActionChains click nút Lưu thất bại: {e}")

    try:
        btn_save = wait.until(_find_save_button)
        driver.execute_script("arguments[0].click();", btn_save)
        print("💾 Đã bấm nút Lưu trong panel-footer bằng JS click")
        return True
    except Exception as e:
        click_errors.append(f"JS click: {e}")
        print(f"⚠ JS click nút Lưu thất bại: {e}")

    try:
        btn_save = wait.until(_find_save_button)
        driver.execute_script("""
            const btn = arguments[0];
            btn.focus();
            btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
            btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
            btn.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true, view: window}));
        """, btn_save)
        print("💾 Đã bấm nút Lưu trong panel-footer bằng MouseEvent")
        return True
    except Exception as e:
        click_errors.append(f"MouseEvent: {e}")
        print(f"⚠ MouseEvent click nút Lưu thất bại: {e}")

    try:
        form = btn_save.find_element(By.XPATH, "ancestor::form")
        driver.execute_script("arguments[0].submit();", form)
        print("💾 Đã submit form chứa nút Lưu")
        return True
    except Exception as e:
        click_errors.append(f"Form submit: {e}")
        print(f"⚠ Submit form thất bại: {e}")

    raise Exception("Không thể bấm nút Lưu trong panel-footer; " + " | ".join(click_errors))


def chon_thua_dat_trung_trong_modal(driver, modal, so_thua, so_to, timeout=20):
    frm_thua_dat = get_active_frm_thua_dat(driver, timeout=timeout)

    item_forms = frm_thua_dat.find_elements(
        By.CSS_SELECTOR,
        "form.item-duplicate[data-duplicate='tt_thuadat']"
    )

    if not item_forms:
        item_forms = frm_thua_dat.find_elements(
            By.CSS_SELECTOR,
            "form.item-duplicate"
        )

    if not item_forms:
        raise Exception(
            "Không tìm thấy form.item-duplicate nào trong frmThuaDat đang active"
        )

    print(f"👉 Tổng số form thửa đất tìm thấy: {len(item_forms)}")

    target_form = None

    for idx, item in enumerate(item_forms):
        try:
            wrappers = item.find_elements(By.CSS_SELECTOR, "div.string-wrapper")
            if not wrappers:
                continue

            text = " ".join(wrappers[0].text.split())

            if not text.strip():
                continue

            print(f"🔎 [{idx}] Kiểm tra: {text[:200]}")

            co_so_thua = bool(re.search(
                rf"Số\s+thứ\s+tự\s+thửa\s*:\s*{re.escape(str(so_thua))}\b",
                text
            ))

            co_so_to = bool(re.search(
                rf"Số\s+hiệu\s+tờ\s+bản\s+đồ\s*:\s*{re.escape(str(so_to))}\b",
                text
            ))

            if co_so_thua and co_so_to:
                print(f"✅ Tìm thấy: thửa={so_thua}, tờ={so_to} tại index [{idx}]")
                target_form = item
                break

        except Exception as e:
            print(f"⚠ Bỏ qua form [{idx}] vì lỗi: {e}")
            continue

    if target_form is None:
        print(f"❌ Không tìm thấy thửa={so_thua}, tờ={so_to}.")
        print("📋 Dump tất cả string-wrapper hiện có:")

        for i, item in enumerate(item_forms):
            try:
                wrappers = item.find_elements(By.CSS_SELECTOR, "div.string-wrapper")
                if wrappers:
                    print(f"  [{i}] {wrappers[0].text[:200]}")
                else:
                    print(f"  [{i}] (không có string-wrapper)")
            except Exception as e:
                print(f"  [{i}] Lỗi: {e}")

        raise Exception(
            f"Không tìm thấy form thửa số_thứ_tự={so_thua}, tờ={so_to} "
            f"trong frmThuaDat đang active"
        )

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});", target_form
    )

    for attempt in range(10):
        driver.execute_script("arguments[0].click();", target_form)

        class_name = target_form.get_attribute("class") or ""

        if "item-selected" in class_name:
            print(f"✅ Đã select thửa={so_thua}, tờ={so_to} sau {attempt + 1} lần click")
            return target_form

        try:
            wrappers = target_form.find_elements(By.CSS_SELECTOR, "div.string-wrapper")
            if wrappers:
                driver.execute_script("arguments[0].click();", wrappers[0])

                class_name = target_form.get_attribute("class") or ""

                if "item-selected" in class_name:
                    print(f"✅ Đã select thửa={so_thua}, tờ={so_to} qua string-wrapper")
                    return target_form
        except:
            pass

    raise Exception(
        f"Đã click 10 lần nhưng thửa={so_thua}, tờ={so_to} chưa có class item-selected"
    )


# =========================================================
# XÓA THỬA TRÙNG - CHỈ 1 HÀM DUY NHẤT
# =========================================================

def xoa_thua_dat_trung_trong_modal(driver, modal, so_thua, so_to, timeout=20):
    """
    Cố gắng xóa thửa trùng bằng Ctrl+Delete.
    Nếu không xóa được, chỉ log và trả về False để vẫn tiếp tục bấm Lưu.
    """

    try:
        target_form = chon_thua_dat_trung_trong_modal(
            driver,
            modal,
            so_thua,
            so_to,
            timeout=timeout,
        )
    except Exception as e:
        print(f"⚠ Không tìm được thửa cần xóa: {e}")
        return False

    print(f"👉 Chuẩn bị xóa thửa={so_thua}, tờ={so_to}")

    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center', inline: 'nearest'});",
        target_form
    )

    try:
        driver.execute_script("arguments[0].click();", target_form)

        wrappers = target_form.find_elements(By.CSS_SELECTOR, "div.string-wrapper")
        if wrappers:
            driver.execute_script("arguments[0].click();", wrappers[0])

    except Exception as e:
        print(f"⚠ Không click focus được form: {e}")

    try:
        ActionChains(driver)\
            .move_to_element(target_form)\
            .click()\
            .key_down(Keys.CONTROL)\
            .send_keys(Keys.DELETE)\
            .key_up(Keys.CONTROL)\
            .perform()

        print(f"⌨ Đã gửi Ctrl + Delete cho thửa={so_thua}, tờ={so_to}")
        return True

    except Exception as e:
        print(f"⚠ Ctrl + Delete thất bại: {e}")
        print(f"⚠ Không xóa được thửa={so_thua}, tờ={so_to}; tiếp tục bấm Lưu")
        return False


# =========================================================
# XÓA TẤT CẢ THỬA TRÙNG VÀ LƯU
# =========================================================

def xoa_tat_ca_thua_trung_va_luu(driver, ds_thua, timeout=20):
    wait = WebDriverWait(driver, timeout)

    ul_selected = wait.until(
        EC.presence_of_element_located(
            (
                By.CSS_SELECTOR,
                "#lstGiayChungNhan ul.vbd-search-item.thuthapthongtin-item.selected",
            )
        )
    )

    btn_edit = ul_selected.find_element(By.CSS_SELECTOR, "a.btnEdit")

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_edit)
    driver.execute_script("arguments[0].click();", btn_edit)

    print("👉 Đã bấm Chỉnh sửa GCN đang chọn")

    tim_modal_thu_thap_chi_tiet(driver, timeout=timeout)
    get_active_frm_thua_dat(driver, timeout=timeout)

    print("✅ Modal/module thu thập thông tin chi tiết đã active")

    thua_da_xoa = []

    for so_thua, so_to in ds_thua:
        print(f"👉 Đang xử lý xóa thửa={so_thua}, tờ={so_to}")

        deleted = xoa_thua_dat_trung_trong_modal(
            driver,
            None,
            so_thua,
            so_to,
            timeout=timeout,
        )

        if deleted:
            thua_da_xoa.append(f"{so_thua}({so_to})")
            print(f"✅ Đã xóa thửa={so_thua}, tờ={so_to}")
        else:
            print(f"⚠ Không xóa được thửa={so_thua}, tờ={so_to} nhưng vẫn tiếp tục bấm Lưu")

        wait_query_done(driver, timeout=25, ajax_wait=1)

    wait_query_done(driver, timeout=25, ajax_wait=1)

    bam_nut_luu_thu_thap_chi_tiet(driver, timeout=timeout)

    print("💾 Đã bấm nút Lưu sau khi xóa tất cả thửa trùng")

    wait_query_done(driver, timeout=35, ajax_wait=2)

    handle_jconfirm_popups(driver, timeout_first=5, timeout_second=2)

    return thua_da_xoa


# =========================================================
# TRA CỨU GCN
# =========================================================

def nhap_ma_gcn_va_tim_kiem(driver, ma_gcn, timeout=20):
    wait = WebDriverWait(driver, timeout)

    input_mahs = wait.until(
        EC.element_to_be_clickable(
            (
                By.CSS_SELECTOR,
                "#wpThongTinTraCuu input[name='soPhatHanh']",
            )
        )
    )

    input_mahs.clear()
    input_mahs.send_keys(ma_gcn)

    print(f"👉 Đã nhập mã GCN: {ma_gcn}")

    btn_search = wait.until(
        EC.element_to_be_clickable((By.ID, "btnSearch"))
    )

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_search)
    driver.execute_script("arguments[0].click();", btn_search)

    print("👉 Đã nhấn nút Tìm kiếm")

    wait_query_done(driver, timeout=45, ajax_wait=3)


def lay_ul_gcn_dau_tien(driver, timeout=20):
    wait = WebDriverWait(driver, timeout)

    wp_ketqua = wait.until(
        EC.presence_of_element_located((By.ID, "wpKetQuaTraCuu"))
    )

    lst_gcn = wait.until(
        lambda d: wp_ketqua.find_element(By.ID, "lstGiayChungNhan")
    )

    uls = lst_gcn.find_elements(
        By.CSS_SELECTOR,
        "ul.vbd-search-item.list-group.thuthapthongtin-item",
    )

    if not uls:
        return None

    return uls[0]


def gcn_da_co_dau_xanh(ul):
    checked_icons = ul.find_elements(
        By.CSS_SELECTOR,
        "span.icon i.fa-check-circle.green",
    )

    return len(checked_icons) > 0


def chon_ul_gcn(driver, ul, timeout=10):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", ul)
    driver.execute_script("arguments[0].click();", ul)

    WebDriverWait(driver, timeout).until(
        lambda d: "selected" in ul.get_attribute("class")
    )

    print("✔ Đã chọn UL GCN thành selected")


# =========================================================
# KIỂM TRA ĐĂNG KÝ
# =========================================================

def bam_kiem_tra_dang_ky(driver, ma_gcn, timeout=15):
    wait = WebDriverWait(driver, timeout)

    btn_kiemtra = wait.until(
        EC.element_to_be_clickable(
            (
                By.CSS_SELECTOR,
                "#wpThongTinChiTiet #btnKiemTraDangKy",
            )
        )
    )

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_kiemtra)
    driver.execute_script("arguments[0].click();", btn_kiemtra)

    print(f"👉 Đã nhấn nút Kiểm tra đăng ký cho GCN: {ma_gcn}")

    wait_query_done(driver, timeout=20, ajax_wait=2)


def kiem_tra_va_xu_ly_thua_trung(driver, ma_gcn, timeout=20, max_lap=5):
    tat_ca_thua_da_xoa = []

    for lan in range(1, max_lap + 1):
        print(f"🔎 Kiểm tra đăng ký lần {lan} cho GCN {ma_gcn}")

        bam_kiem_tra_dang_ky(driver, ma_gcn)

        co_popup, ds_thua, message = handle_popup_thua_dat_ton_tai(driver, timeout=1)

        if co_popup and ds_thua:
            print(f"⚠ Có {len(ds_thua)} thửa trùng, tiến hành xóa")

            thua_da_xoa = xoa_tat_ca_thua_trung_va_luu(
                driver,
                ds_thua,
                timeout=timeout,
            )

            tat_ca_thua_da_xoa.extend(thua_da_xoa)

            print(f"🔁 Đã xóa xong thửa trùng, sẽ kiểm tra lại GCN {ma_gcn}")
            continue

        if co_popup and not ds_thua:
            print("⚠ Có popup nhưng không đọc được danh sách thửa.")
            break

        print("✅ Không còn popup thửa trùng")
        return tat_ca_thua_da_xoa

    raise Exception(
        f"Đã kiểm tra {max_lap} lần nhưng vẫn còn lỗi thửa trùng hoặc chưa xử lý xong"
    )


# =========================================================
# DUYỆT VÀO VẬN HÀNH
# =========================================================

def duyet_vao_van_hanh(driver, ma_gcn, timeout=30):
    wait = WebDriverWait(driver, timeout)

    btn_duyet = wait.until(
        EC.element_to_be_clickable(
            (
                By.CSS_SELECTOR,
                "#wpThongTinChiTiet #btnDuyetDangKy",
            )
        )
    )

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_duyet)
    driver.execute_script("arguments[0].click();", btn_duyet)

    print(f"🚀 Đã nhấn nút Duyệt vào vận hành cho GCN: {ma_gcn}")

    wait_query_done(driver, timeout=35, ajax_wait=2)

    modal = find_visible_element(
        driver,
        "div[id^='mdlDangKyWizard-']",
        timeout=timeout,
    )

    print("✅ Modal Đăng ký Wizard đã load")

    btn_save = wait.until(
        lambda d: modal.find_element(By.CSS_SELECTOR, "#btnSaveDangKy")
    )

    wait.until(lambda d: btn_save.is_displayed() and btn_save.is_enabled())

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_save)
    driver.execute_script("arguments[0].click();", btn_save)

    print(f"💾 Đã nhấn #btnSaveDangKy cho GCN: {ma_gcn}")

    handle_popup_orange_after_save_dangky(driver, timeout=8)

    wait_query_done(driver, timeout=30, ajax_wait=2)

    handle_jconfirm_popups(driver, timeout_first=3, timeout_second=2)

    try:
        close_btn = modal.find_element(By.CSS_SELECTOR, "div.modal-header button.close")

        if close_btn.is_displayed():
            driver.execute_script("arguments[0].click();", close_btn)

            WebDriverWait(driver, 10).until(
                EC.invisibility_of_element(modal)
            )

            print("🔒 Đã đóng modal wizard sau khi lưu")

    except:
        pass

    return True


# =========================================================
# XỬ LÝ 1 GCN
# =========================================================

def xu_ly_mot_gcn(driver, ten_file, ma_gcn):
    try:
        nhap_ma_gcn_va_tim_kiem(driver, ma_gcn)

        ul = lay_ul_gcn_dau_tien(driver)

        if ul is None:
            return {
                "TrangThai": "Không tìm thấy bản ghi",
                "ThuaDaXoa": "",
                "GhiChu": "Không có kết quả trong #lstGiayChungNhan",
            }

        if gcn_da_co_dau_xanh(ul):
            return {
                "TrangThai": "Đã duyệt từ trước",
                "ThuaDaXoa": "",
                "GhiChu": "Có icon fa-check-circle green",
            }

        chon_ul_gcn(driver, ul)

        thua_da_xoa = kiem_tra_va_xu_ly_thua_trung(driver, ma_gcn)

        duyet_vao_van_hanh(driver, ma_gcn)

        if thua_da_xoa:
            trang_thai = "Đã xóa thửa trùng và duyệt vận hành"
            ghi_chu = "Đã xử lý thửa trùng trước khi duyệt"
        else:
            trang_thai = "Đã duyệt vận hành"
            ghi_chu = "Không có thửa trùng"

        return {
            "TrangThai": trang_thai,
            "ThuaDaXoa": ", ".join(thua_da_xoa),
            "GhiChu": ghi_chu,
        }

    except Exception as e:
        traceback.print_exc()

        return {
            "TrangThai": "Lỗi",
            "ThuaDaXoa": "",
            "GhiChu": str(e),
        }


# =========================================================
# MAIN AUTOMATION
# =========================================================

def run_automation(username, password, maxa, folder_path):
    driver = None

    try:
        ds_files = lay_danh_sach_gcn_tu_folder(folder_path)

        if not ds_files:
            messagebox.showwarning("Không có file", "Folder không có file PDF.")
            return

        csv_path = tao_file_ket_qua(folder_path)

        options = Options()
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach", True)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        wait = WebDriverWait(driver, 30)

        driver.get(BASE_URL)

        username_box, password_box = get_login_fields(wait)

        username_box.clear()
        username_box.send_keys(username)

        password_box.clear()
        password_box.send_keys(password)
        password_box.send_keys(Keys.ENTER)

        messagebox.showinfo(
            "Info",
            "Đăng nhập thành công! Nhấn OK để bắt đầu tự động hoá.",
        )

        option_xpath = f"//select[@id='ddlPhuongXa']/option[@value='{maxa}']"

        option_element = wait.until(
            EC.element_to_be_clickable((By.XPATH, option_xpath))
        )

        option_element.click()

        print(f"✅ Đã chọn phường/xã: {maxa}")

        for idx, (ten_file, ma_gcn) in enumerate(ds_files, start=1):
            print("=" * 80)
            print(f"FILE {idx}/{len(ds_files)}: {ten_file}")
            print(f"Mã GCN: {ma_gcn}")

            ket_qua = xu_ly_mot_gcn(driver, ten_file, ma_gcn)

            row = {
                "STT": idx,
                "TenFile": ten_file,
                "MaGCN": ma_gcn,
                "TrangThai": ket_qua["TrangThai"],
                "ThuaDaXoa": ket_qua["ThuaDaXoa"],
                "GhiChu": ket_qua["GhiChu"],
                "ThoiGian": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

            ghi_ket_qua(csv_path, row)

            print(f"📌 Kết quả: {ket_qua['TrangThai']}")
            print(f"🧾 Thửa đã xóa: {ket_qua['ThuaDaXoa']}")
            print(f"📝 Ghi chú: {ket_qua['GhiChu']}")

        messagebox.showinfo(
            "Hoàn tất",
            f"Đã xử lý xong folder.\nFile kết quả:\n{csv_path}",
        )

    except Exception as e:
        traceback.print_exc()

        messagebox.showerror(
            "Lỗi",
            f"Có lỗi xảy ra trong quá trình tự động hoá:\n{e}",
        )

    finally:
        if driver:
            pass


# =========================================================
# GUI
# =========================================================

def browse_folder(folder_var):
    folder = filedialog.askdirectory(title="Chọn folder chứa file PDF")

    if folder:
        folder_var.set(folder)


def start_automation_thread(username, password, maxa, folder_path):
    if not all([username, password, maxa, folder_path]):
        messagebox.showwarning(
            "Thiếu thông tin",
            "Vui lòng nhập đầy đủ Username, Password, Mã xã và Folder PDF.",
        )
        return

    automation_thread = threading.Thread(
        target=run_automation,
        args=(username, password, maxa, folder_path),
        daemon=True,
    )

    automation_thread.start()


def create_gui():
    root = tk.Tk()
    root.title("Tool Tự Động Duyệt Vận Hành - Đắk Lắk")

    frame = ttk.Frame(root, padding="20")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    ttk.Label(frame, text="Username:").grid(column=0, row=0, sticky=tk.W, pady=5)

    username_entry = ttk.Entry(frame, width=45)
    username_entry.grid(column=1, row=0, sticky=(tk.W, tk.E), columnspan=2)

    ttk.Label(frame, text="Password:").grid(column=0, row=1, sticky=tk.W, pady=5)

    password_entry = ttk.Entry(frame, show="*", width=45)
    password_entry.grid(column=1, row=1, sticky=(tk.W, tk.E), columnspan=2)

    ttk.Label(frame, text="Mã xã/phường:").grid(column=0, row=2, sticky=tk.W, pady=5)

    maxa_entry = ttk.Entry(frame, width=45)
    maxa_entry.grid(column=1, row=2, sticky=(tk.W, tk.E), columnspan=2)

    ttk.Label(frame, text="Folder PDF:").grid(column=0, row=3, sticky=tk.W, pady=5)

    folder_var = tk.StringVar()

    folder_entry = ttk.Entry(frame, textvariable=folder_var, width=45)
    folder_entry.grid(column=1, row=3, sticky=(tk.W, tk.E))

    btn_browse = ttk.Button(
        frame,
        text="Chọn folder",
        command=lambda: browse_folder(folder_var),
    )

    btn_browse.grid(column=2, row=3, padx=5)

    start_button = ttk.Button(
        frame,
        text="Bắt đầu",
        command=lambda: start_automation_thread(
            username_entry.get().strip(),
            password_entry.get().strip(),
            maxa_entry.get().strip(),
            folder_var.get().strip(),
        ),
    )

    start_button.grid(column=0, row=4, columnspan=3, pady=20)

    ttk.Label(
        frame,
        text="URL cố định: https://dla.mplis.gov.vn/dc/ThuThapThongTin",
    ).grid(column=0, row=5, columnspan=3, sticky=tk.W, pady=5)

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    root.mainloop()


if __name__ == "__main__":
    create_gui()
