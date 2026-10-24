"""
Tool Duyệt Vận Hành theo danh sách Excel - Đắk Lắk

Flow mỗi GCN:
    1. Nhập số phát hành -> Tìm kiếm -> lấy kết quả
    2. Có dấu xanh -> "Đã duyệt từ trước"; chưa có -> chọn GCN
    3. Duyệt vào vận hành -> Lưu đăng ký -> xác nhận popup

Mỗi bước chờ đúng response của request tương ứng (bắt qua CDP performance log),
không dùng time.sleep() cố định.
"""

import re
import os
import csv
import json
import time
import threading
import traceback
import unicodedata
import winsound
from datetime import datetime

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import openpyxl

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


BASE_URL = "https://dla.mplis.gov.vn/dc/ThuThapThongTin"

# =========================================================
# ENDPOINT CỦA TỪNG BƯỚC (regex khớp với URL request)
# False = thao tác không gửi request -> chỉ chờ DOM
# None  = chưa biết endpoint -> chờ tới khi hết XHR/Fetch (network idle)
#         và ghi toàn bộ request vào network_log_*.txt để xác định endpoint.
# list  = nhiều request nối tiếp nhau, chờ lần lượt từng cái
# =========================================================

AJAX = r"/dc/ThuThapThongTinAjax/"

ENDPOINTS = {
    "chon_xa": False,       # chọn phường/xã ở #ddlPhuongXa
    "tim_kiem": AJAX + r"GetThuThapThongTinGiayChungNhan",
    "chon_gcn": False,      # click chọn GCN trong #lstGiayChungNhan
    "mo_wizard": [          # bấm #btnDuyetDangKy -> load modal wizard
        AJAX + r"ValidateThuThapThongTin",
        AJAX + r"ConvertThongTinDangKy",
    ],
}

# bấm #btnSaveDangKy -> popup xác nhận -> bấm Đồng ý -> validate -> (slider captcha) -> save
EP_VALIDATE_DANG_KY = r"/dc/DangKyAjax/ValidateThongTinDangKy"
EP_SAVE_DANG_KY = AJAX + r"SaveThongTinDangKy"
EP_SLIDER_CHALLENGE = r"/dc/SliderCaptcha/Challenge"
EP_SLIDER_VERIFY = r"/dc/SliderCaptcha/Verify"

# Sau validate mà không thấy request Save trong khoảng này (và đang có popup chặn)
# thì coi như không lưu được (vd: thửa đất đã được đăng ký)
SAVE_GRACE = 5

WIZARD_CSS = "div[id^='mdlDangKyWizard-']"

# Số lần chạy lại 1 GCN khi bị gián đoạn bởi captcha / hết phiên đăng nhập
MAX_LAN_CAPTCHA = 3

# Captcha hiện giữa lúc chờ request (vd sau khi bấm Đồng ý duyệt): tool đứng chờ
# người dùng giải tối đa chừng này giây, không tính vào timeout của request
CAPTCHA_MAX_WAIT = 600

NETWORK_TIMEOUT = 45

POPUP_CSS = "div.jconfirm.jconfirm-vbdlis-theme.jconfirm-open"

# Nội dung popup xác nhận sau khi bấm #btnSaveDangKy (so sánh chữ thường)
XAC_NHAN_DUYET_TEXT = "muốn duyệt dữ liệu này vào vận hành"

SUCCESS_KEYS = ("success", "Success", "isSuccess", "IsSuccess", "IsSuccessful")


# =========================================================
# THEO DÕI NETWORK (CDP)
# =========================================================

class NetworkError(Exception):
    pass


class NetworkWatcher:
    """
    Đọc sự kiện Network.* từ performance log của ChromeDriver.
    mark() xoá mọi request cũ -> chỉ theo dõi request phát sinh SAU hành động.
    """

    XHR_TYPES = ("XHR", "Fetch")

    def __init__(self, driver, log_path, pause_check=None):
        self.driver = driver
        self.log_path = log_path
        self.requests = {}
        self.order = 0
        # pause_check() True (vd đang hiện captcha) -> ngừng đếm timeout, chờ người dùng
        self.pause_check = pause_check
        self.captcha_pending = False
        self.captcha_challenge_id = None
        self._checked_body_ids = set()
        self._last_beep = 0
        self._paused_total = 0

    def dang_captcha(self):
        dom_captcha = bool(self.pause_check and self.pause_check())
        return self.captcha_pending or dom_captcha

    def tam_dung(self, dt):
        """
        Gọi mỗi vòng chờ với dt = thời gian vòng vừa rồi. Nếu đang captcha: nhắc người
        dùng, cộng dồn thời gian tạm dừng và trả về dt (để cộng vào hạn chờ); không thì 0.
        """
        if not self.dang_captcha():
            self._paused_total = 0
            self._last_beep = 0
            return 0

        self._paused_total += dt

        if self._paused_total > CAPTCHA_MAX_WAIT:
            self.captcha_pending = False
            raise NetworkError(f"Captcha chưa được giải sau {CAPTCHA_MAX_WAIT}s")

        if time.time() - self._last_beep > 8:
            self._last_beep = time.time()
            cid = f" (challengeId={self.captcha_challenge_id})" if self.captcha_challenge_id else ""
            print(f"🧩 Đang hiện Captcha kéo puzzle{cid} -> hãy kéo giải trên Chrome, tool đang tạm dừng chờ...")
            try:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

        return dt

    def _inspect_for_captcha(self, r):
        """Theo dõi /dc/SliderCaptcha/Challenge và /dc/SliderCaptcha/Verify."""
        if r["type"] not in self.XHR_TYPES or r["id"] in self._checked_body_ids:
            return
        self._checked_body_ids.add(r["id"])

        url = r["url"] or ""
        body = self._get_body(r)

        if re.search(EP_SLIDER_CHALLENGE, url, re.I) or (
            body and '"challengeId"' in body and '"piece"' in body and '"bg"' in body
        ):
            data = {}
            if body:
                try:
                    data = json.loads(body)
                except Exception:
                    pass
            cid = data.get("challengeId")
            self.captcha_pending = True
            self.captcha_challenge_id = cid
            self._last_beep = 0
            self._log("SLIDER_CAPTCHA", [f"Challenge challengeId={cid} {r['method']} {url}"])
            print(f"🧩 [SliderCaptcha] Hiện bảng kéo puzzle (challengeId={cid}) -> đang tạm dừng chờ bạn kéo...")
            return

        if re.search(EP_SLIDER_VERIFY, url, re.I):
            data = {}
            if body:
                try:
                    data = json.loads(body)
                except Exception:
                    pass
            if data.get("verified") is True:
                self.captcha_pending = False
                self.captcha_challenge_id = None
                self._log("SLIDER_CAPTCHA", [f"Verify OK (recaptchaResponse={data.get('recaptchaResponse')})"])
                print("✅ [SliderCaptcha] Giải puzzle thành công! Tiếp tục lưu đăng ký...")
            else:
                self.captcha_pending = True
                self._last_beep = 0
                self._log("SLIDER_CAPTCHA", [f"Verify FAILED: {body}"])
                print("⚠ [SliderCaptcha] Kéo chưa khớp, hãy kéo lại trên Chrome...")
            return

        if self.captcha_pending and r["status"] and 200 <= r["status"] < 300:
            if any(ep in url for ep in (
                "GetThuThapThongTinGiayChungNhan",
                "ValidateThuThapThongTin",
                "ConvertThongTinDangKy",
                "ValidateThongTinDangKy",
                "SaveThongTinDangKy",
            )):
                self.captcha_pending = False
                self.captcha_challenge_id = None

    def _pump(self):
        for entry in self.driver.get_log("performance"):
            try:
                msg = json.loads(entry["message"])["message"]
            except Exception:
                continue

            method = msg.get("method", "")
            params = msg.get("params", {})
            rid = params.get("requestId")

            if method == "Network.requestWillBeSent":
                req = params.get("request", {})
                url = req.get("url", "")
                self.order += 1
                self.requests[rid] = {
                    "id": rid,
                    "url": url,
                    "method": req.get("method", ""),
                    "type": params.get("type"),
                    "order": self.order,
                    "status": None,
                    "done": False,
                    "error": None,
                }
                # Bật cờ tạm dừng ngay lập tức khi vừa phát sinh request lấy SliderCaptcha/Challenge
                if re.search(EP_SLIDER_CHALLENGE, url, re.I):
                    self.captcha_pending = True
                    self._last_beep = 0

            elif rid in self.requests:
                r = self.requests[rid]

                if method == "Network.responseReceived":
                    r["status"] = params.get("response", {}).get("status")
                    r["type"] = params.get("type") or r["type"]

                elif method == "Network.loadingFinished":
                    r["done"] = True
                    self._inspect_for_captcha(r)

                elif method == "Network.loadingFailed":
                    r["done"] = True
                    r["error"] = params.get("errorText") or "loadingFailed"

    def mark(self):
        self._pump()
        self.requests.clear()

    def _log(self, step, lines):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%H:%M:%S}] ===== {step} =====\n")
            for line in lines:
                f.write(f"    {line}\n")

    def _xhr_requests(self):
        return sorted(
            (r for r in self.requests.values() if r["type"] in self.XHR_TYPES),
            key=lambda r: r["order"],
        )

    def _get_body(self, r):
        try:
            res = self.driver.execute_cdp_cmd(
                "Network.getResponseBody", {"requestId": r["id"]}
            )
            return res.get("body", "")
        except Exception:
            return None

    def _check_response(self, step, r, strict_json=True):
        """Raise NetworkError nếu response lỗi. Trả về (body, json|None)."""
        if r["error"]:
            raise NetworkError(
                f"[{step}] Request lỗi: {r['method']} {r['url']} -> {r['error']}"
            )

        body = self._get_body(r)

        if r["status"] is None or not (200 <= r["status"] < 300):
            raise NetworkError(
                f"[{step}] HTTP {r['status']}: {r['method']} {r['url']}\n"
                f"Body: {(body or '')[:500]}"
            )

        data = None
        if body:
            try:
                data = json.loads(body)
            except Exception:
                data = None

        if strict_json and isinstance(data, dict):
            for key in SUCCESS_KEYS:
                if key in data and not data[key]:
                    raise NetworkError(
                        f"[{step}] Server báo thất bại ({key}=false): {r['url']}\n"
                        f"Body: {body[:500]}"
                    )

        return body, data

    def find(self, url_pattern):
        """Request đầu tiên (sau mark()) khớp url_pattern, hoặc None. Gọi sau _pump()."""
        regex = re.compile(url_pattern, re.I)

        for r in sorted(self.requests.values(), key=lambda r: r["order"]):
            if regex.search(r["url"]):
                return r

        return None

    def finish(self, step, r, strict_json=True):
        """Log + kiểm tra 1 request đã xong, trả về dict response."""
        self._log(step, [f"{r['method']} {r['status']} {r['url']}"])
        body, data = self._check_response(step, r, strict_json=strict_json)
        print(f"🌐 [{step}] {r['status']} {r['url']}")
        return {"url": r["url"], "status": r["status"], "body": body, "json": data}

    def poll(self):
        self._pump()

    def wait_for(self, step, url_pattern, timeout=NETWORK_TIMEOUT, on_tick=None,
                 strict_json=True):
        """Chờ request khớp url_pattern (phát sinh sau mark()) hoàn tất và hợp lệ."""
        end_time = time.time() + timeout

        while time.time() < end_time:
            tick = time.time()
            self._pump()

            if on_tick:
                on_tick()

            r = self.find(url_pattern)

            if r and r["done"]:
                return self.finish(step, r, strict_json=strict_json)

            time.sleep(0.1)
            end_time += self.tam_dung(time.time() - tick)

        self._log(step, [f"TIMEOUT chờ /{url_pattern}/"] + self._describe_all())
        raise NetworkError(
            f"[{step}] Timeout {timeout}s chờ response khớp /{url_pattern}/"
        )

    def wait_idle(self, step, timeout=NETWORK_TIMEOUT, first_request_wait=3,
                  quiet=0.8, on_tick=None):
        """
        Chưa biết endpoint: chờ tới khi mọi XHR/Fetch phát sinh sau mark() xong
        và mạng im lặng `quiet` giây. Ghi toàn bộ request vào log.
        """
        start = time.time()
        end_time = start + timeout
        last_activity = None

        while time.time() < end_time:
            self._pump()

            if on_tick:
                on_tick()

            xhrs = self._xhr_requests()

            if not xhrs:
                if time.time() - start > first_request_wait:
                    self._log(step, ["(không có XHR/Fetch nào)"])
                    return []
            else:
                pending = [r for r in xhrs if not r["done"]]
                if pending:
                    last_activity = time.time()
                elif last_activity is None:
                    last_activity = time.time()
                elif time.time() - last_activity >= quiet:
                    self._log(step, self._describe_all())
                    for r in xhrs:
                        print(f"🌐 [{step}] {r['method']} {r['status']} {r['url']}")
                        self._check_response(step, r)
                    return xhrs

            time.sleep(0.1)

        self._log(step, ["TIMEOUT network idle"] + self._describe_all())
        pending = [r["url"] for r in self._xhr_requests() if not r["done"]]
        raise NetworkError(f"[{step}] Timeout {timeout}s, request còn treo: {pending}")

    def _describe_all(self):
        return [
            f"{r['method']} {r['status']} {r['type']} "
            f"{'DONE' if r['done'] else 'PENDING'} {r['error'] or ''} {r['url']}"
            for r in sorted(self.requests.values(), key=lambda r: r["order"])
            if r["type"] in self.XHR_TYPES or r["type"] == "Document"
        ]

    def wait_step(self, step, on_tick=None, timeout=NETWORK_TIMEOUT):
        pattern = ENDPOINTS.get(step)

        if pattern is False:
            return None

        if isinstance(pattern, (list, tuple)):
            return [
                self.wait_for(step, p, timeout=timeout, on_tick=on_tick)
                for p in pattern
            ]

        if pattern:
            return self.wait_for(step, pattern, timeout=timeout, on_tick=on_tick)

        return self.wait_idle(step, timeout=timeout, on_tick=on_tick)


# =========================================================
# DOM HELPERS
# =========================================================

def wait_dom_settled(driver, timeout=15):
    """Sau khi response về, chờ JS render xong (jQuery hết active, hết loading mask)."""
    def _ok(d):
        return d.execute_script("""
            const busy = window.jQuery ? jQuery.active : 0;
            const masks = [...document.querySelectorAll('div.jquery-loading-modal_bg')]
                .filter(e => e.offsetParent !== null);
            return busy === 0 && masks.length === 0;
        """)

    WebDriverWait(driver, timeout).until(_ok)


def find_visible_element(driver, css_selector, timeout=20):
    def _find(d):
        for el in d.find_elements(By.CSS_SELECTOR, css_selector):
            try:
                if el.is_displayed():
                    return el
            except Exception:
                pass
        return False

    return WebDriverWait(driver, timeout).until(_find)


def js_click(driver, el):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    driver.execute_script("arguments[0].click();", el)


def dong_sach_modal_va_overlay(driver):
    if gap_captcha_hoac_dang_nhap(driver):
        return
    try:
        driver.execute_script("""
            document.querySelectorAll('.modal.in, .modal.show').forEach(m => {
                try {
                    if (window.jQuery) {
                        jQuery(m).modal('hide');
                    }
                } catch(e) {}

                m.classList.remove('in');
                m.classList.remove('show');
                m.style.display = 'none';
                m.setAttribute('aria-hidden', 'true');
            });

            document.querySelectorAll('.jconfirm, .modal-backdrop, div.jquery-loading-modal_bg, .popover')
                .forEach(e => e.remove());

            document.body.classList.remove('modal-open');
            document.body.style.paddingRight = '';
            document.body.style.overflow = '';
        """)
    except Exception as e:
        print("⚠ Không dọn được modal/overlay:", e)


def _chu(s):
    """Chuẩn hoá chữ tiếng Việt (NFC, gộp khoảng trắng, chữ thường) để so sánh."""
    return unicodedata.normalize("NFC", " ".join((s or "").split())).lower()


def tim_popup_xac_nhan_duyet(driver):
    """
    Popup "Bạn có chắc chắn muốn duyệt dữ liệu này vào vận hành không?"
    đang mở và có nút "Đồng ý" -> (popup, nút). Không có -> None.
    """
    try:
        popup = popup_chan_dang_mo(driver)

        if popup is None:
            return None

        if _chu(XAC_NHAN_DUYET_TEXT) not in _chu(popup.text):
            return None

        btn = nut_dong_y(popup)

        if btn is None:
            return None

        return popup, btn

    except Exception:
        return None


def nut_dong_y(popup):
    """
    Nút 'Đồng ý' của jConfirm, hoặc None. Ưu tiên nút cam:
    div.jconfirm-scrollpane > div > div > div > div > div.jconfirm-buttons > button.btn.btn-orange
    """
    btn = _visible(popup.find_elements(
        By.CSS_SELECTOR,
        ":scope > div.jconfirm-scrollpane > div > div > div > div > div.jconfirm-buttons > button.btn.btn-orange",
    )) or _visible(popup.find_elements(By.CSS_SELECTOR, "div.jconfirm-buttons > button.btn.btn-orange"))

    if btn is not None:
        return btn

    for btn in popup.find_elements(By.CSS_SELECTOR, "div.jconfirm-buttons > button"):
        try:
            if btn.is_displayed() and _chu(btn.text) == "đồng ý":
                return btn
        except Exception:
            pass

    return None


def bam_va_cho_dong(driver, popup, btn):
    """Bấm nút và chắc chắn popup/modal đã đóng. JS click không ăn thì click chuột thật."""
    try:
        nhan = " ".join(btn.text.split()) or "nút đóng"
    except Exception:
        nhan = "nút"

    cach_bam = [
        ("JS click", lambda: driver.execute_script("arguments[0].click();", btn)),
        ("click chuột", lambda: ActionChains(driver).move_to_element(btn).pause(0.2).click().perform()),
        ("click Selenium", btn.click),
    ]

    for ten, bam in cach_bam:
        try:
            bam()
            WebDriverWait(driver, 3).until(EC.invisibility_of_element(popup))
            print(f"✅ Đã bấm '{nhan}' ({ten})")
            return
        except Exception as e:
            print(f"⚠ Bấm bằng {ten} chưa đóng được: {type(e).__name__}")

    raise Exception("Bấm 3 cách nhưng popup/modal vẫn chưa đóng")


def _visible(els):
    for el in els:
        try:
            if el.is_displayed():
                return el
        except Exception:
            pass
    return None


def popup_chan_dang_mo(driver):
    """Bảng jConfirm đang mở đè lên wizard (vd thửa đã được đăng ký), hoặc None."""
    return _visible(driver.find_elements(By.CSS_SELECTOR, POPUP_CSS))


def dong_bang_va_wizard(driver, timeout=10):
    """
    Đóng lần lượt: bảng jConfirm đè lên -> wizard
    (#mdlDangKyWizard-* > div > div > div.modal-header > button).
    Trả về danh sách nội dung bảng đã đóng.
    """
    messages = []

    for _ in range(10):
        jc = popup_chan_dang_mo(driver)

        if jc is not None:
            content = _visible(jc.find_elements(By.CSS_SELECTOR, ".jconfirm-content, .jconfirm-message"))
            messages.append(" ".join((content or jc).text.split())[:300])
            btn = nut_dong_y(jc) \
                or _visible(jc.find_elements(By.CSS_SELECTOR, ".jconfirm-closeIcon")) \
                or _visible(jc.find_elements(By.CSS_SELECTOR, "div.jconfirm-buttons > button"))
            target = jc

        else:
            target = _visible(driver.find_elements(By.CSS_SELECTOR, WIZARD_CSS))

            if target is None:
                break

            btn = _visible(target.find_elements(
                By.CSS_SELECTOR, ":scope > div > div > div.modal-header > button"
            )) or _visible(target.find_elements(By.CSS_SELECTOR, "div.modal-header button.close"))

        if btn is None:
            raise Exception(f"Không tìm thấy nút đóng cho: {(target.get_attribute('id') or target.text)[:100]}")

        bam_va_cho_dong(driver, target, btn)

    else:
        raise Exception("Đóng popup/wizard 10 lần vẫn còn mở")

    for m in messages:
        print(f"💬 Đã đóng: {m}")

    print("🔒 Đã đóng bảng/wizard")
    return messages


# =========================================================
# EXCEL -> DANH SÁCH GCN
# =========================================================

def doc_danh_sach_gcn_tu_excel(excel_path, ten_cot="Số phát hành"):
    wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)

    try:
        ws = wb.worksheets[0]
        rows = ws.iter_rows(values_only=True)

        col_idx = None
        for _ in range(10):
            header = next(rows, None)
            if header is None:
                break
            for i, v in enumerate(header):
                if v is not None and str(v).strip().lower() == ten_cot.strip().lower():
                    col_idx = i
                    break
            if col_idx is not None:
                break

        if col_idx is None:
            raise Exception(f"Không tìm thấy cột '{ten_cot}' trong 10 dòng đầu sheet '{ws.title}'")

        ds = []
        da_co = set()

        for row in rows:
            if col_idx >= len(row) or row[col_idx] is None:
                continue

            ma = " ".join(str(row[col_idx]).split())

            if ma and ma not in da_co:
                da_co.add(ma)
                ds.append(ma)

        return ds

    finally:
        wb.close()


# =========================================================
# CSV KẾT QUẢ
# =========================================================

def ghi_ket_qua(csv_path, row):
    file_exists = os.path.exists(csv_path)

    with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["STT", "MaGCN", "TrangThai", "GhiChu", "ThoiGian"],
        )

        if not file_exists:
            writer.writeheader()

        writer.writerow(row)


# =========================================================
# CÁC BƯỚC
# =========================================================

def get_login_fields(wait):
    username_box = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[autocomplete='username'], input[name='username']")
        )
    )

    password_box = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, "input[autocomplete='current-password'], input[name='password']")
        )
    )

    return username_box, password_box


def chon_phuong_xa(driver, watcher, maxa, timeout=40):
    ddl = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.ID, "ddlPhuongXa"))
    )
    WebDriverWait(driver, timeout).until(
        lambda d: ddl.find_elements(By.CSS_SELECTOR, f"option[value='{maxa}']")
    )

    watcher.mark()
    Select(ddl).select_by_value(maxa)
    watcher.wait_step("chon_xa")
    wait_dom_settled(driver)

    print(f"✅ Đã chọn phường/xã: {maxa}")


def reset_trang(driver, watcher, maxa):
    print("🔄 Tải lại trang để làm sạch trạng thái...")
    watcher.captcha_pending = False
    watcher.captcha_challenge_id = None
    driver.get(BASE_URL)
    chon_phuong_xa(driver, watcher, maxa)


# =========================================================
# CAPTCHA / HẾT PHIÊN ĐĂNG NHẬP
# =========================================================

def gap_captcha_hoac_dang_nhap(driver):
    """True nếu đang hiện captcha (bao gồm puzzle bg/piece base64) hoặc bị đẩy ra trang đăng nhập."""
    try:
        return driver.execute_script("""
            const visible = el => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && s.opacity !== '0';
            };
            const css = [
                "input[name='password']", "input[autocomplete='current-password']",
                "[id*='captcha' i]", "[class*='captcha' i]", "[name*='captcha' i]",
                "[id*='puzzle' i]", "[class*='puzzle' i]", "[id*='jigsaw' i]", "[class*='jigsaw' i]",
                "[id*='challenge' i]", "[name*='challenge' i]",
                "img[src*='captcha' i]", "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']",
                "iframe[src*='turnstile']", "iframe[title*='captcha' i]"
            ].join(',');
            if ([...document.querySelectorAll(css)].some(visible)) {
                return true;
            }
            // Nhận diện cặp ảnh base64 của puzzle captcha (bg: data:image/jpeg;base64, piece: data:image/png;base64)
            const hasBg = [...document.querySelectorAll("img[src^='data:image/jpeg;base64,']")].some(visible);
            const hasPiece = [...document.querySelectorAll("img[src^='data:image/png;base64,']")].some(visible);
            if (hasBg && hasPiece) {
                return true;
            }
            return false;
        """)
    except Exception:
        return False


def cho_giai_captcha(driver, watcher, username, password, maxa):
    """Dừng lại cho người dùng tự giải captcha / đăng nhập lại, rồi vào lại trang làm việc."""
    print("🧩 Gặp captcha hoặc hết phiên đăng nhập -> chờ người dùng xử lý")

    while True:
        # Điền sẵn user/pass nếu ô đang trống, người dùng chỉ cần giải captcha
        try:
            for css, value in (
                ("input[autocomplete='username'], input[name='username']", username),
                ("input[autocomplete='current-password'], input[name='password']", password),
            ):
                box = _visible(driver.find_elements(By.CSS_SELECTOR, css))
                if box is not None and not box.get_attribute("value"):
                    box.send_keys(value)
        except Exception:
            pass

        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

        messagebox.showwarning(
            "Gặp captcha",
            "Website đang hiện captcha hoặc yêu cầu đăng nhập lại.\n\n"
            "Hãy giải captcha / đăng nhập trên cửa sổ Chrome,\n"
            "xong rồi bấm OK để tool chạy tiếp.",
        )

        if not gap_captcha_hoac_dang_nhap(driver):
            break

        print("⚠ Vẫn còn captcha/trang đăng nhập, chờ tiếp")

    reset_trang(driver, watcher, maxa)
    print("✅ Đã xử lý captcha, chạy tiếp")


def _chuan_hoa_ma(s):
    return re.sub(r"\s+", "", s or "").upper()


def tim_kiem_gcn(driver, watcher, ma_gcn, timeout=20):
    """Bước 1: tìm GCN, trả về UL kết quả khớp mã (hoặc None)."""
    dong_sach_modal_va_overlay(driver)

    input_mahs = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#wpThongTinTraCuu input[name='soPhatHanh']"))
    )
    input_mahs.click()
    input_mahs.send_keys(Keys.CONTROL, "a")
    input_mahs.send_keys(Keys.DELETE)
    input_mahs.send_keys(ma_gcn)

    btn_search = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.ID, "btnSearch"))
    )

    watcher.mark()
    js_click(driver, btn_search)
    print(f"👉 Đã tìm kiếm mã GCN: {ma_gcn}")

    watcher.wait_step("tim_kiem")
    wait_dom_settled(driver)

    uls = driver.find_elements(
        By.CSS_SELECTOR,
        "#wpKetQuaTraCuu #lstGiayChungNhan ul.vbd-search-item.list-group.thuthapthongtin-item",
    )

    if not uls:
        return None

    if len(uls) == 1:
        return uls[0]

    ma = _chuan_hoa_ma(ma_gcn)
    for ul in uls:
        if ma in _chuan_hoa_ma(ul.text):
            return ul

    raise Exception(f"Có {len(uls)} kết quả nhưng không kết quả nào khớp mã {ma_gcn}")


def gcn_da_co_dau_xanh(ul):
    return len(ul.find_elements(By.CSS_SELECTOR, "span.icon i.fa-check-circle.green")) > 0


def chon_gcn(driver, watcher, ul, timeout=15):
    watcher.mark()
    js_click(driver, ul)

    WebDriverWait(driver, timeout).until(
        lambda d: "selected" in (ul.get_attribute("class") or "")
    )

    watcher.wait_step("chon_gcn")
    wait_dom_settled(driver)

    print("✔ Đã chọn GCN")


def duyet_vao_van_hanh(driver, watcher, ma_gcn, timeout=30):
    """Bước duyệt: mở wizard -> Lưu đăng ký -> xác nhận -> đóng."""
    btn_duyet = WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "#wpThongTinChiTiet #btnDuyetDangKy"))
    )

    watcher.mark()
    js_click(driver, btn_duyet)
    print(f"🚀 Đã bấm Duyệt vào vận hành: {ma_gcn}")

    watcher.wait_step("mo_wizard")
    wait_dom_settled(driver)

    modal = find_visible_element(driver, WIZARD_CSS, timeout=timeout)

    btn_save = WebDriverWait(driver, timeout).until(
        lambda d: modal.find_element(By.CSS_SELECTOR, "#btnSaveDangKy")
    )
    WebDriverWait(driver, timeout).until(
        lambda d: btn_save.is_displayed() and btn_save.is_enabled()
    )

    # 1. Bấm "Duyệt vào vận hành" (#btnSaveDangKy): chưa gửi request,
    #    chỉ hiện popup xác nhận -> chờ popup
    js_click(driver, btn_save)
    print(f"💾 Đã bấm Duyệt vào vận hành (#btnSaveDangKy): {ma_gcn}")

    try:
        popup, btn_dong_y = WebDriverWait(driver, timeout).until(tim_popup_xac_nhan_duyet)
    except TimeoutException:
        dang_mo = popup_chan_dang_mo(driver)
        raise Exception(
            f"Không thấy popup xác nhận duyệt sau {timeout}s. Popup đang mở: "
            f"{' '.join(dang_mo.text.split())[:300] if dang_mo else '(không có)'}"
        )

    # 2. Bấm "Đồng ý" -> lúc này mới gửi ValidateThongTinDangKy rồi SaveThongTinDangKy
    watcher.mark()
    bam_va_cho_dong(driver, popup, btn_dong_y)

    watcher.wait_for("luu_dang_ky", EP_VALIDATE_DANG_KY, strict_json=False)

    # 3. Chờ Save. Validate xong mà quá SAVE_GRACE giây chưa gửi Save -> bị chặn
    #    (vd bảng jConfirm báo thửa đất đã được đăng ký).
    save = None
    validate_xong = time.time()
    end_time = validate_xong + NETWORK_TIMEOUT

    while time.time() < end_time:
        tick = time.time()
        watcher.poll()
        r = watcher.find(EP_SAVE_DANG_KY)

        if r and r["done"]:
            # Save: server báo thành công bằng HTTP 2xx, không cần đọc body
            save = watcher.finish("luu_dang_ky", r, strict_json=False)
            break

        time.sleep(0.1)

        # Đang captcha thì không tính giờ (cả timeout lẫn SAVE_GRACE)
        dung = watcher.tam_dung(time.time() - tick)
        if dung > 0:
            end_time += dung
            validate_xong = time.time()
            continue

        if r is None and time.time() - validate_xong > SAVE_GRACE:
            break

    else:
        raise NetworkError(
            f"[luu_dang_ky] Timeout {NETWORK_TIMEOUT}s chờ /{EP_SAVE_DANG_KY}/ hoàn tất"
        )

    wait_dom_settled(driver)

    # Có thể vẫn hiện bảng (vd thửa đã được đăng ký) -> bấm Đồng ý + tắt wizard
    messages = dong_bang_va_wizard(driver)
    ghi_chu = " | ".join(m for m in messages if m)

    if save is None:
        return "Không lưu được", ghi_chu or "Bị chặn sau ValidateThongTinDangKy"

    return "Đã duyệt vận hành", ghi_chu


def xu_ly_mot_gcn(driver, watcher, ma_gcn):
    ul = tim_kiem_gcn(driver, watcher, ma_gcn)

    if ul is None:
        return "Không tìm thấy bản ghi", "Không có kết quả trong #lstGiayChungNhan"

    if gcn_da_co_dau_xanh(ul):
        return "Đã duyệt từ trước", "Có icon fa-check-circle green"

    chon_gcn(driver, watcher, ul)

    return duyet_vao_van_hanh(driver, watcher, ma_gcn)


# =========================================================
# MAIN AUTOMATION
# =========================================================

def run_automation(username, password, maxa, excel_path, ten_cot):
    driver = None

    try:
        ds_gcn = doc_danh_sach_gcn_tu_excel(excel_path, ten_cot)

        if not ds_gcn:
            messagebox.showwarning("Không có dữ liệu", f"Cột '{ten_cot}' không có mã GCN nào.")
            return

        out_dir = os.path.dirname(os.path.abspath(excel_path))
        now = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = os.path.join(out_dir, f"ket_qua_duyet_excel_{now}.csv")
        log_path = os.path.join(out_dir, f"network_log_{now}.txt")

        print(f"📄 Đọc được {len(ds_gcn)} mã GCN từ Excel")

        options = Options()
        options.add_argument("--start-maximized")
        options.add_experimental_option("detach", True)
        options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd("Network.enable", {})

        watcher = NetworkWatcher(
            driver, log_path,
            pause_check=lambda: gap_captcha_hoac_dang_nhap(driver),
        )

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

        if gap_captcha_hoac_dang_nhap(driver):
            cho_giai_captcha(driver, watcher, username, password, maxa)
        else:
            chon_phuong_xa(driver, watcher, maxa)

        for idx, ma_gcn in enumerate(ds_gcn, start=1):
            print("=" * 80)
            print(f"GCN {idx}/{len(ds_gcn)}: {ma_gcn}")

            # Gặp captcha giữa chừng -> chờ người dùng giải rồi chạy lại đúng GCN này
            for lan_thu in range(1, MAX_LAN_CAPTCHA + 1):
                if watcher.dang_captcha():
                    cho_giai_captcha(driver, watcher, username, password, maxa)

                try:
                    trang_thai, ghi_chu = xu_ly_mot_gcn(driver, watcher, ma_gcn)
                    break

                except Exception as e:
                    traceback.print_exc()
                    trang_thai, ghi_chu = "Lỗi", str(e)

                    if watcher.dang_captcha() and lan_thu < MAX_LAN_CAPTCHA:
                        print(f"🧩 Lỗi do captcha/hết phiên, sẽ chạy lại GCN {ma_gcn}")
                        continue

                    try:
                        dong_sach_modal_va_overlay(driver)
                        reset_trang(driver, watcher, maxa)
                    except Exception as e2:
                        if not watcher.dang_captcha():
                            raise Exception(f"Không khôi phục được trang sau lỗi: {e2}")
                    break

            ghi_ket_qua(csv_path, {
                "STT": idx,
                "MaGCN": ma_gcn,
                "TrangThai": trang_thai,
                "GhiChu": ghi_chu,
                "ThoiGian": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })

            print(f"📌 Kết quả: {trang_thai}")
            print(f"📝 Ghi chú: {ghi_chu}")

        messagebox.showinfo(
            "Hoàn tất",
            f"Đã xử lý xong {len(ds_gcn)} GCN.\nFile kết quả:\n{csv_path}\n"
            f"Network log:\n{log_path}",
        )

    except Exception as e:
        traceback.print_exc()

        messagebox.showerror(
            "Lỗi",
            f"Có lỗi xảy ra trong quá trình tự động hoá:\n{e}",
        )


# =========================================================
# GUI
# =========================================================

def browse_excel(excel_var):
    path = filedialog.askopenfilename(
        title="Chọn file Excel danh sách GCN",
        filetypes=[("Excel", "*.xlsx *.xlsm"), ("All files", "*.*")],
    )

    if path:
        excel_var.set(path)


def start_automation_thread(username, password, maxa, excel_path, ten_cot):
    if not all([username, password, maxa, excel_path, ten_cot]):
        messagebox.showwarning(
            "Thiếu thông tin",
            "Vui lòng nhập đầy đủ Username, Password, Mã xã, File Excel và Tên cột.",
        )
        return

    threading.Thread(
        target=run_automation,
        args=(username, password, maxa, excel_path, ten_cot),
        daemon=True,
    ).start()


def create_gui():
    root = tk.Tk()
    root.title("Tool Duyệt Vận Hành theo Excel - Đắk Lắk")

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

    ttk.Label(frame, text="File Excel:").grid(column=0, row=3, sticky=tk.W, pady=5)
    excel_var = tk.StringVar()
    ttk.Entry(frame, textvariable=excel_var, width=45).grid(column=1, row=3, sticky=(tk.W, tk.E))
    ttk.Button(
        frame,
        text="Chọn file",
        command=lambda: browse_excel(excel_var),
    ).grid(column=2, row=3, padx=5)

    ttk.Label(frame, text="Tên cột mã GCN:").grid(column=0, row=4, sticky=tk.W, pady=5)
    cot_var = tk.StringVar(value="Số phát hành")
    ttk.Entry(frame, textvariable=cot_var, width=45).grid(column=1, row=4, sticky=(tk.W, tk.E), columnspan=2)

    ttk.Button(
        frame,
        text="Bắt đầu",
        command=lambda: start_automation_thread(
            username_entry.get().strip(),
            password_entry.get().strip(),
            maxa_entry.get().strip(),
            excel_var.get().strip(),
            cot_var.get().strip(),
        ),
    ).grid(column=0, row=5, columnspan=3, pady=20)

    ttk.Label(frame, text=f"URL cố định: {BASE_URL}").grid(
        column=0, row=6, columnspan=3, sticky=tk.W, pady=5
    )

    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)

    root.mainloop()


if __name__ == "__main__":
    create_gui()
