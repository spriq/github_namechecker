import requests
import random
import string
import time
import sys
import urllib3
import os
import threading

# ---------------- 配置区域 ----------------
# Clash: 7890, V2Ray/SSR: 1080 或 10809
PROXY_PORT = 7897

# 线程数量
THREAD_COUNT = 10

# 设置要生成的类型：
# 1 = 纯字母 (4位) - 极难
# 2 = 字母+数字 (4位) - 容易很多
MODE = 1
# ----------------------------------------

# 禁用安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 配置代理
PROXIES = {
    "http": f"http://127.0.0.1:{PROXY_PORT}",
    "https": f"http://127.0.0.1:{PROXY_PORT}",
}

# 全局变量与锁
total_scanned = 0
found_count = 0
start_time = time.time()
found_names_set = set()  # 用于内存去重
stop_event = threading.Event()  # 用于优雅停止线程

# 锁：用于确保打印和文件写入不冲突
print_lock = threading.Lock()
file_lock = threading.Lock()


def load_existing_names():
    """启动前读取已保存的用户名，防止重复记录"""
    if os.path.exists("available_names.txt"):
        with open("available_names.txt", "r", encoding="utf-8") as f:
            for line in f:
                name = line.strip()
                if name:
                    found_names_set.add(name)
        print(f"[*] 已加载历史记录: {len(found_names_set)} 个用户名")


def get_random_name(mode=1):
    """生成随机 4 位字符串"""
    if mode == 1:
        chars = string.ascii_lowercase
    else:
        chars = string.ascii_lowercase + string.digits
    return ''.join(random.choices(chars, k=4))


def save_result(username):
    """线程安全地写入文件"""
    with file_lock:
        # 双重检查：确保写入前没有被其他线程抢先写入（虽然概率极低）
        if username in found_names_set:
            return

        found_names_set.add(username)
        with open("available_names.txt", "a", encoding="utf-8") as f:
            f.write(f"{username}\n")


def check_github_username(username):
    url = f"https://github.com/{username}"
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/92.0.4515.107 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:90.0) Gecko/20100101 Firefox/90.0"
    ]
    headers = {"User-Agent": random.choice(ua_list)}

    try:
        response = requests.get(url, headers=headers, proxies=PROXIES, verify=False, timeout=10)
        if response.status_code == 404:
            return True
        elif response.status_code == 200:
            return False
        elif response.status_code == 429:
            return "LIMIT"
        else:
            return False
    except:
        return False


def worker_thread(thread_id):
    """工作线程逻辑"""
    global total_scanned, found_count

    while not stop_event.is_set():
        username = get_random_name(MODE)

        # 如果内存里已经有了，直接跳过，不发请求
        if username in found_names_set:
            continue

        status = check_github_username(username)

        # 更新全局计数器
        # 注意：简单的 += 在多线程下不完全安全，但只用于显示统计误差可接受
        # 若追求严谨需加锁，但会降低速度
        total_scanned += 1

        if status is True:
            # 再次检查是否被重复记录（防止并发写入）
            if username not in found_names_set:
                with print_lock:
                    found_count += 1
                    print(f"\n[★ T{thread_id}] 发现可用: {username}")
                    print(f"       注册 -> https://github.com/signup")
                save_result(username)

        elif status == "LIMIT":
            with print_lock:
                print(f"\n[!] 线程 T{thread_id} 触发 429 限流，暂停 30 秒...")
            time.sleep(30)

        # 稍微随机延迟，避免10个线程像DDoS一样攻击GitHub
        time.sleep(random.uniform(0.5, 1.5))


def print_progress():
    """独立的线程用于刷新进度条，避免多线程打印冲突"""
    while not stop_event.is_set():
        elapsed = time.time() - start_time
        speed = total_scanned / elapsed if elapsed > 0 else 0

        # 使用 \r 回车符覆盖当前行
        msg = f"\r[*] 扫描中... | 总计: {total_scanned} | 命中: {found_count} | 速度: {speed:.1f}次/秒"
        sys.stdout.write(msg)
        sys.stdout.flush()
        time.sleep(0.5)


def main():
    print("--- GitHub 4位用户名多线程挖掘机 ---")
    print(f"[*] 模式: {'纯字母' if MODE == 1 else '字母+数字'}")
    print(f"[*] 线程数: {THREAD_COUNT}")
    print(f"[*] 代理: 127.0.0.1:{PROXY_PORT}")

    load_existing_names()
    print("[*] 开始挖掘 (按 Ctrl+C 停止)...\n")

    # 启动工作线程
    threads = []
    for i in range(THREAD_COUNT):
        t = threading.Thread(target=worker_thread, args=(i + 1,))
        t.daemon = True  # 设置为守护线程，主程序退出时自动结束
        t.start()
        threads.append(t)

    # 启动进度显示线程
    p_thread = threading.Thread(target=print_progress)
    p_thread.daemon = True
    p_thread.start()

    try:
        # 主线程保持运行，直到用户按 Ctrl+C
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\n--- 正在停止所有线程... ---")
        stop_event.set()
        print(f"本次运行共找到 {found_count} 个新用户名。")
        print("请查看 available_names.txt")


if __name__ == "__main__":
    main()
