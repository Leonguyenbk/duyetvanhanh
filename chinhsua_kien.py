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

base_url = "https://qlkh.vnedutech.vn/Account/Login"

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

input("Đăng nhập thành công, nhấn Enter để tiếp tục...")
