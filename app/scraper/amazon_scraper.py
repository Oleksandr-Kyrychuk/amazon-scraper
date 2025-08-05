import time
import random
import logging
import sqlite3
import tempfile
import os
from contextlib import contextmanager
from fake_useragent import UserAgent
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
from app.database import init_db, save_to_db

# Налаштування логування
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler()
    ]
)

def check_db_contents(db_path):
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM products")
        count = c.fetchone()[0]
        logging.info(f"База даних містить {count} записів")
        if count > 0:
            c.execute("SELECT * FROM products LIMIT 5")
            rows = c.fetchall()
            for row in rows:
                logging.info(
                    f"ASIN: {row[0]}, Назва: {row[1]}, Ціна: {row[2]}, Оригінальна ціна: {row[3]}, Рейтинг: {row[4]}, Відгуки: {row[5]}, Доставка: {row[6]}, Продавець: {row[7]}, URL: {row[8]}")
        conn.close()
    except sqlite3.Error as e:
        logging.error(f"Помилка перевірки бази даних: {e}")

def get_price_from_soup(soup):
    try:
        # Спроба знайти ціну через a-offscreen
        price_elem = soup.select_one(
            "span.a-price.aok-align-center.reinventPricePriceToPayMargin.priceToPay span.a-offscreen, "
            "span.a-price span.a-offscreen, "
            "span#priceblock_ourprice, "
            "span#priceblock_dealprice"
        )
        if price_elem and price_elem.text.strip():
            price_text = price_elem.text.strip().replace('$', '').replace(',', '')
            if price_text.replace('.', '').isdigit():
                logging.debug(f"Знайдено ціну через a-offscreen: {price_text}")
                return float(price_text)

        # Резервний варіант: комбінація a-price-whole і a-price-fraction
        whole_elem = soup.select_one("span.a-price-whole")
        fraction_elem = soup.select_one("span.a-price-fraction")
        if whole_elem and fraction_elem:
            whole_text = whole_elem.text.strip().replace(',', '')
            fraction_text = fraction_elem.text.strip()
            price_text = f"{whole_text}.{fraction_text}"
            if price_text.replace('.', '').isdigit():
                logging.debug(f"Знайдено ціну через a-price-whole і a-price-fraction: {price_text}")
                return float(price_text)

        # Додатковий селектор для блоку ціни
        price_block = soup.select_one("div#corePriceDisplay_desktop_feature_div span.a-price")
        if price_block:
            price_text = price_block.text.strip().replace('$', '').replace(',', '')
            if price_text.replace('.', '').isdigit():
                logging.debug(f"Знайдено ціну через corePriceDisplay: {price_text}")
                return float(price_text)

        logging.debug("Ціна не знайдена за жодним селектором")
        return 0.0
    except Exception as e:
        logging.error(f"Помилка парсингу ціни: {e}")
        return 0.0

def get_original_price_from_soup(soup):
    try:
        original_price_elem = soup.select_one(
            "span.a-price.a-text-price span.a-offscreen, "
            "span.a-price[data-a-strike='true'] span.a-offscreen, "
            "span#listPrice, "
            "span.a-price[data-a-color='secondary'] span.a-offscreen"
        )
        if original_price_elem and original_price_elem.text.strip():
            original_price_text = original_price_elem.text.strip().replace('$', '').replace(',', '')
            if original_price_text.replace('.', '').isdigit():
                logging.debug(f"Знайдено оригінальну ціну через a-offscreen: {original_price_text}")
                return float(original_price_text)

        # Резервний варіант для знижок
        discount_elem = soup.select_one("span.a-price[data-a-strike='true']")
        if discount_elem:
            whole_elem = discount_elem.select_one("span.a-price-whole")
            fraction_elem = discount_elem.select_one("span.a-price-fraction")
            if whole_elem and fraction_elem:
                whole_text = whole_elem.text.strip().replace(',', '')
                fraction_text = fraction_elem.text.strip()
                price_text = f"{whole_text}.{fraction_text}"
                if price_text.replace('.', '').isdigit():
                    logging.debug(f"Знайдено оригінальну ціну через a-price-whole і a-price-fraction: {price_text}")
                return float(price_text)

        logging.debug("Оригінальна ціна не знайдена за жодним селектором")
        return 0.0
    except Exception as e:
        logging.error(f"Помилка парсингу оригінальної ціни: {e}")
        return 0.0

def get_title_from_soup(soup):
    try:
        title_elem = soup.select_one("h1#title span#productTitle, span#productTitle, h2 a span, h2 span.a-text-normal")
        return title_elem.text.strip() if title_elem else "N/A"
    except Exception as e:
        logging.error(f"Помилка парсингу назви: {e}")
        return "N/A"

def get_rating_from_soup(soup):
    try:
        rating_elem = soup.select_one(
            "span[data-hook='average-star-rating'] span.a-icon-alt, i[data-hook='average-star-rating'], span[aria-label*='out of 5 stars'], span.a-icon-alt")
        if rating_elem:
            rating_text = rating_elem.text.split()[0] if 'data-hook' in rating_elem.attrs or 'a-icon-alt' in rating_elem.get('class', []) else rating_elem['aria-label'].split()[0]
            return float(rating_text) if rating_text.replace('.', '').isdigit() else 0.0
        logging.debug("Рейтинг не знайдено за жодним селектором")
        return 0.0
    except Exception as e:
        logging.error(f"Помилка парсингу рейтингу: {e}")
        return 0.0

def get_reviews_from_soup(soup):
    try:
        reviews_elem = soup.select_one(
            "span[data-hook='total-review-count'], a#acrCustomerReviewText, span[aria-label*='ratings']")
        if reviews_elem:
            reviews_text = reviews_elem.text.strip().replace(',', '').replace('ratings', '').replace('rating', '')
            reviews_text = ''.join(filter(str.isdigit, reviews_text))
            return int(reviews_text) if reviews_text.isdigit() else 0
        logging.debug("Елемент відгуків не знайдено")
        return 0
    except Exception as e:
        logging.error(f"Помилка парсингу кількості відгуків: {e}")
        return 0

def get_seller_from_soup(soup):
    try:
        seller_elem = soup.select_one(
            "a#sellerProfileTriggerId, div#merchantInfo a, div#soldBy a, div#merchant-info span")
        if seller_elem:
            seller_text = seller_elem.text.strip()
            if "Sold by" in seller_text:
                seller_text = seller_text.replace("Sold by", "").replace(":", "").strip()
            if not seller_text:
                return "Amazon.com"
            logging.debug(f"Знайдено продавця: {seller_text}")
            return seller_text
        logging.debug("Продавець не знайдений")
        return "N/A"
    except Exception as e:
        logging.error(f"Помилка парсингу продавця: {e}")
        return "N/A"

def get_delivery_from_soup(soup):
    try:
        delivery_elem = soup.select_one(
            "div#deliveryBlockMessage span, div#availability span, div#availability_feature_div span, span.a-size-base.a-color-secondary")
        if delivery_elem:
            delivery_text = delivery_elem.text.strip()
            logging.debug(f"Знайдено інформацію про доставку: {delivery_text}")
            return delivery_text
        logging.debug("Інформація про доставку не знайдена")
        return "N/A"
    except Exception as e:
        logging.error(f"Помилка парсингу доставки: {e}")
        return "N/A"

def is_captcha_present(driver):
    return any(keyword in driver.page_source.lower() for keyword in ["captcha", "meow", "verify your identity"])

class AmazonScraper:
    def __init__(self, query="laptop", pages=1, db_path="amazon.db", headless=True):
        self.query = query
        self.pages = pages
        self.db_path = db_path
        self.ua = UserAgent(browsers=['chrome', 'firefox', 'edge'], os=['windows', 'macos'])
        self.cancelled = False
        self.current_page = 0
        self.total_products = 0
        self.headless = headless
        init_db(db_path)

    def cancel(self):
        self.cancelled = True
        logging.info("Скрапінг скасовано")

    @contextmanager
    def create_driver(self):
        options = Options()
        user_agent = self.ua.random
        options.add_argument(f"user-agent={user_agent}")
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-features=UserAgentClientHint,TranslateUI")
        options.add_argument("--blink-settings=imagesEnabled=true")
        options.add_argument("--enable-javascript")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-devtools")
        options.add_argument("--no-zygote")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-extensions")
        options.add_argument("--incognito")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-background-networking")

        tmpdirname = tempfile.mkdtemp()
        logging.debug(f"Створено тимчасову директорію: {tmpdirname}")
        options.add_argument(f"--user-data-dir={tmpdirname}")

        log_path = os.path.join(tmpdirname, "chrome_debug.log")
        logging.debug(f"Шлях до логу ChromeDriver: {log_path}")
        service = Service(ChromeDriverManager().install(), log_path=log_path)

        logging.debug(f"Ініціалізація WebDriver з User-Agent: {user_agent}")
        try:
            driver = webdriver.Chrome(service=service, options=options)
            driver.delete_all_cookies()
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": f"""
                    Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
                    Object.defineProperty(navigator, 'platform', {{ get: () => 'Win32' }});
                    Object.defineProperty(navigator, 'userAgent', {{ get: () => '{user_agent}' }});
                    Object.defineProperty(window, 'chrome', {{ get: () => {{ runtime: {{}} }} }});
                    Object.defineProperty(navigator, 'plugins', {{ get: () => [1, 2, 3] }});
                    Object.defineProperty(navigator, 'languages', {{ get: () => ['en-US', 'en'] }});
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{ get: () => 4 }});
                    Object.defineProperty(navigator, 'deviceMemory', {{ get: () => 8 }});
                """
            })
            width = random.randint(1600, 1920)
            height = random.randint(900, 1080)
            driver.set_window_size(width, height)
            logging.debug(f"Встановлено розмір вікна: {width}x{height}")
            yield driver
        except Exception as e:
            logging.error(f"Помилка створення WebDriver: {e}")
            raise
        finally:
            try:
                driver.quit()
                logging.info("WebDriver закрито")
            except Exception as e:
                logging.error(f"Помилка закриття WebDriver: {e}")
            finally:
                try:
                    if os.path.exists(tmpdirname):
                        for root, dirs, files in os.walk(tmpdirname, topdown=False):
                            for name in files:
                                os.remove(os.path.join(root, name))
                            for name in dirs:
                                os.rmdir(os.path.join(root, name))
                        os.rmdir(tmpdirname)
                        logging.debug(f"Тимчасова директорія видалена: {tmpdirname}")
                except Exception as e:
                    logging.error(f"Помилка видалення тимчасової директорії {tmpdirname}: {e}")

    def human_scroll(self, driver):
        if self.cancelled:
            raise Exception("Скрапінг скасовано")
        logging.debug("Імітація людського скролу")
        actions = ActionChains(driver)
        scroll_points = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
        for i in range(len(scroll_points) - 1):
            if self.cancelled:
                raise Exception("Скрапінг скасовано")
            start = scroll_points[i]
            end = scroll_points[i + 1]
            driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {start});")
            time.sleep(random.uniform(3.0, 6.0))
            actions.scroll_by_amount(0, random.randint(100, 300)).pause(random.uniform(0.5, 1.5)).perform()
            driver.execute_script(f"window.scrollTo(0, document.body.scrollHeight * {end});")
            time.sleep(random.uniform(5.0, 10.0))

    def human_mouse_movement(self, driver):
        if self.cancelled:
            raise Exception("Скрапінг скасовано")
        logging.debug("Імітація рухів миші")
        try:
            actions = ActionChains(driver)
            for _ in range(random.randint(3, 6)):
                x_offset = random.randint(-150, 150)
                y_offset = random.randint(-150, 150)
                actions.move_by_offset(x_offset, y_offset).pause(random.uniform(0.7, 2.0)).perform()
                time.sleep(random.uniform(0.5, 1.0))
            actions.reset_actions()
        except Exception as e:
            logging.error(f"Помилка імітації рухів миші: {e}")

    def random_interaction(self, driver):
        if self.cancelled:
            raise Exception("Скрапінг скасовано")
        logging.debug("Виконання випадкової взаємодії")
        try:
            interactive_elements = driver.find_elements(By.CSS_SELECTOR,
                                                        "a.s-ref-text-link, div.s-filter-bar a, span.a-button-text")
            if interactive_elements and random.random() < 0.3:
                element = random.choice(interactive_elements)
                actions = ActionChains(driver)
                actions.move_to_element(element).pause(random.uniform(0.7, 1.5)).click().perform()
                logging.info(f"Виконано клік по елементу: {element.text[:50]}...")
                time.sleep(random.uniform(5.0, 10.0))
        except Exception as e:
            logging.error(f"Помилка випадкової взаємодії: {e}")

    def check_captcha(self, driver, max_retries=5):
        for attempt in range(max_retries):
            if self.cancelled:
                raise Exception("Скрапінг скасовано")
            try:
                if is_captcha_present(driver):
                    logging.warning(f"Виявлено CAPTCHA (спроба {attempt + 1}/{max_retries})")
                    driver.save_screenshot(f"blocked_page_attempt_{attempt + 1}.png")
                    with open(f"captcha_page_attempt_{attempt + 1}.html", "w", encoding="utf-8") as f:
                        f.write(driver.page_source)
                    logging.debug("Збережено HTML і скріншот CAPTCHA для діагностики")
                    if not self.headless:
                        logging.warning("Очікування ручного вирішення CAPTCHA (30 секунд)")
                        time.sleep(30)
                    else:
                        logging.warning("Автоматичне вирішення CAPTCHA не підтримується в headless-режимі")
                    if attempt < max_retries - 1:
                        driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": self.ua.random})
                        driver.delete_all_cookies()
                        driver.refresh()
                        time.sleep(random.uniform(10, 15))
                        continue
                    logging.warning("Не вдалося пройти CAPTCHA, але продовжуємо зі спробою введення запиту")
                    return False
                return True
            except Exception as e:
                logging.error(f"Помилка перевірки CAPTCHA (спроба {attempt + 1}): {e}")
                with open(f"captcha_error_page_attempt_{attempt + 1}.html", "w", encoding="utf-8") as f:
                    f.write(driver.page_source)
                if attempt < max_retries - 1:
                    driver.execute_cdp_cmd("Network.setUserAgentOverride", {"userAgent": self.ua.random})
                    driver.delete_all_cookies()
                    driver.refresh()
                    time.sleep(random.uniform(10, 15))
                    continue
                logging.warning("Не вдалося перевірити CAPTCHA, але продовжуємо зі спробою введення запиту")
                return False

    def parse_product_page(self, driver, product_url, retries=3):
        if self.cancelled:
            raise Exception("Скрапінг скасовано")
        logging.info(f"Парсинг сторінки товару: {product_url}")
        for attempt in range(retries):
            if self.cancelled:
                raise Exception("Скрапінг скасовано")
            try:
                original_window = driver.current_window_handle
                driver.execute_script(f"window.open('{product_url}');")
                driver.switch_to.window(driver.window_handles[-1])

                logging.info(f"Спроба {attempt + 1}: Відкриваємо сторінку товару: {product_url}")
                WebDriverWait(driver, 20).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "h1#title, span#productTitle")),
                        EC.presence_of_element_located((By.CSS_SELECTOR, "span.a-price, div#buybox, div#availability, div#corePriceDisplay_desktop_feature_div"))
                    )
                )
                time.sleep(random.uniform(5, 10))
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "span.a-price-whole, span.a-offscreen"))
                    )
                    logging.debug("Елемент ціни завантажено")
                except TimeoutException:
                    logging.warning("Елемент ціни не завантажено після очікування")

                self.human_scroll(driver)
                self.human_mouse_movement(driver)
                self.random_interaction(driver)

                soup = BeautifulSoup(driver.page_source, "html.parser")
                with open(f"product_page_{product_url.split('/')[-1]}_attempt_{attempt + 1}.html", "w",
                          encoding="utf-8") as f:
                    f.write(driver.page_source)

                if self.check_captcha(driver):
                    wait_attempts = 0
                    while is_captcha_present(driver) and wait_attempts < 6:
                        if self.cancelled:
                            raise Exception("Скрапінг скасовано")
                        logging.warning("CAPTCHA ще не вирішено. Очікуємо...")
                        time.sleep(random.uniform(5, 10))
                        wait_attempts += 1
                    if is_captcha_present(driver):
                        logging.warning(f"Не вдалося пройти CAPTCHA на сторінці товару: {product_url}")
                        driver.close()
                        driver.switch_to.window(original_window)
                        if attempt < retries - 1:
                            time.sleep(random.uniform(10, 15))
                            continue
                        return {
                            "title": "N/A",
                            "price": 0.0,
                            "original_price": 0.0,
                            "rating": 0.0,
                            "reviews": 0,
                            "seller": "N/A",
                            "delivery": "N/A"
                        }
                    logging.info("CAPTCHA вирішено або відсутнє, продовжуємо...")

                availability_elem = soup.select_one(
                    "div#availability span, span#outOfStock, span:-soup-contains('No featured offers available'), span:-soup-contains('Currently unavailable')")
                if availability_elem and ("No featured offers available" in availability_elem.text or "Currently unavailable" in availability_elem.text):
                    logging.warning(f"Товар недоступний: {product_url}, текст: '{availability_elem.text.strip()}'")
                    with open(f"unavailable_product_page_{product_url.split('/')[-1]}_attempt_{attempt + 1}.html", "w",
                              encoding="utf-8") as f:
                        f.write(driver.page_source)
                    driver.close()
                    driver.switch_to.window(original_window)
                    product_data = {
                        "title": get_title_from_soup(soup),
                        "price": 0.0,
                        "original_price": 0.0,
                        "rating": 0.0,
                        "reviews": 0,
                        "seller": "N/A",
                        "delivery": "N/A"
                    }
                    logging.info(f"Повертаємо дані для недоступного товару: {product_data}")
                    return product_data

                title = get_title_from_soup(soup)
                price = get_price_from_soup(soup)
                original_price = get_original_price_from_soup(soup)
                if price == 0.0 and original_price > 0.0:
                    price = original_price
                    logging.debug(f"Використано оригінальну ціну як основну: {price}")
                elif price == 0.0 and original_price == 0.0:
                    logging.warning(f"Ціна та оригінальна ціна = 0.0 для {product_url}. Можливо, товар недоступний або ціна не спарсилась.")
                    price_block = soup.select_one("div#corePriceDisplay_desktop_feature_div, span.a-price, div#buybox")
                    logging.debug(f"HTML блоку ціни: {price_block.prettify() if price_block else 'Відсутній'}")

                rating = get_rating_from_soup(soup)
                reviews = get_reviews_from_soup(soup)
                seller = get_seller_from_soup(soup)
                delivery = get_delivery_from_soup(soup)

                if seller == "N/A" or "See All Buying Options" in seller:
                    try:
                        see_options_btn = driver.find_element(By.CSS_SELECTOR, "a#buybox-see-all-buying-choices")
                        actions = ActionChains(driver)
                        actions.move_to_element(see_options_btn).pause(random.uniform(0.7, 1.5)).click().perform()
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, "div#buyingOptionsList"))
                        )
                        soup = BeautifulSoup(driver.page_source, "html.parser")
                        price = get_price_from_soup(soup)
                        seller = get_seller_from_soup(soup)
                        if price == 0.0:
                            logging.warning(f"Ціна все ще 0.0 після перевірки пропозицій сторонніх продавців для {product_url}")
                    except Exception as e:
                        logging.error(f"Помилка при парсингу пропозицій сторонніх продавців: {e}")

                driver.close()
                driver.switch_to.window(original_window)
                product_data = {
                    "title": title,
                    "price": price,
                    "original_price": original_price,
                    "rating": rating,
                    "reviews": reviews,
                    "seller": seller,
                    "delivery": delivery
                }
                logging.info(f"Успішно спарсено сторінку товару: {product_url}, дані: {product_data}")
                return product_data

            except (TimeoutException, NoSuchElementException) as e:
                logging.error(f"Спроба {attempt + 1}: Помилка парсингу сторінки товару {product_url}: {e}")
                with open(f"error_product_page_{product_url.split('/')[-1]}_attempt_{attempt + 1}.html", "w",
                          encoding="utf-8") as f:
                    f.write(driver.page_source)
                try:
                    driver.close()
                    driver.switch_to.window(original_window)
                except Exception as e:
                    logging.error(f"Помилка при закритті вкладки: {e}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(10, 15))
                    continue
                product_data = {
                    "title": "N/A",
                    "price": 0.0,
                    "original_price": 0.0,
                    "rating": 0.0,
                    "reviews": 0,
                    "seller": "N/A",
                    "delivery": "N/A"
                }
                logging.info(f"Повертаємо дані за замовчуванням після невдалих спроб: {product_data}")
                return product_data
            except Exception as e:
                logging.error(f"Спроба {attempt + 1}: Невідома помилка парсингу сторінки товару {product_url}: {e}")
                with open(f"error_product_page_{product_url.split('/')[-1]}_attempt_{attempt + 1}.html", "w",
                          encoding="utf-8") as f:
                    f.write(driver.page_source)
                try:
                    driver.close()
                    driver.switch_to.window(original_window)
                except Exception as e:
                    logging.error(f"Помилка при закритті вкладки: {e}")
                if attempt < retries - 1:
                    time.sleep(random.uniform(10, 15))
                    continue
                product_data = {
                    "title": "N/A",
                    "price": 0.0,
                    "original_price": 0.0,
                    "rating": 0.0,
                    "reviews": 0,
                    "seller": "N/A",
                    "delivery": "N/A"
                }
                logging.info(f"Повертаємо дані за замовчуванням після невдалих спроб: {product_data}")
                return product_data

    def run(self, task_id=None, max_retries=2):
        from app.main import scrape_tasks

        def update_progress():
            if task_id and task_id in scrape_tasks:
                scrape_tasks[task_id]["current_page"] = self.current_page
                scrape_tasks[task_id]["total_products"] = self.total_products

        for retry in range(max_retries):
            if self.cancelled:
                logging.info(f"Спроба {retry + 1}: Скрапінг скасовано до початку")
                break

            try:
                with self.create_driver() as driver:
                    for attempt in range(3):
                        if self.cancelled:
                            raise Exception("Скрапінг скасовано")
                        try:
                            logging.info(f"Спроба {attempt + 1}: Завантаження головної сторінки Amazon")
                            driver.get("https://www.amazon.com/")
                            time.sleep(random.uniform(10, 15))
                            self.human_mouse_movement(driver)
                            self.random_interaction(driver)
                            if not self.check_captcha(driver):
                                logging.warning("CAPTCHA виявлено, але продовжуємо з введенням запиту")
                                break
                            logging.info("CAPTCHA відсутнє або вирішено, продовжуємо...")
                            break
                        except Exception as e:
                            logging.error(f"Помилка завантаження головної сторінки (спроба {attempt + 1}): {e}")
                            if attempt < 2:
                                time.sleep(random.uniform(10, 15))
                                continue
                            raise

                    if self.cancelled:
                        raise Exception("Скрапінг скасовано")

                    try:
                        logging.info(f"Введення пошукового запиту: {self.query}")
                        search_input = WebDriverWait(driver, 20).until(
                            EC.presence_of_element_located((By.ID, "twotabsearchtextbox"))
                        )
                        search_input.clear()
                        for ch in self.query:
                            if self.cancelled:
                                raise Exception("Скрапінг скасовано")
                            actions = ActionChains(driver)
                            actions.move_to_element(search_input).click().send_keys(ch).perform()
                            time.sleep(random.uniform(0.3, 0.7))
                        logging.info(f"Пошуковий запит '{self.query}' успішно введено")
                    except TimeoutException:
                        logging.error("Не вдалося знайти пошукове поле")
                        with open("main_page.html", "w", encoding="utf-8") as f:
                            f.write(driver.page_source)
                        raise

                    try:
                        search_button = driver.find_element(By.ID, "nav-search-submit-button")
                        actions = ActionChains(driver)
                        actions.move_to_element(search_button).pause(random.uniform(0.7, 1.5)).click().perform()
                        logging.info("Натискання кнопки пошуку виконано")
                        time.sleep(random.uniform(10, 15))
                    except NoSuchElementException:
                        logging.error("Не вдалося знайти кнопку пошуку")
                        with open("search_button_error.html", "w", encoding="utf-8") as f:
                            f.write(driver.page_source)
                        raise

                    for page in range(1, self.pages + 1):
                        if self.cancelled:
                            raise Exception("Скрапінг скасовано")
                        self.current_page = page
                        logging.info(f"Обробка сторінки результатів {page}/{self.pages}")

                        for attempt in range(3):
                            if self.cancelled:
                                raise Exception("Скрапінг скасовано")
                            try:
                                WebDriverWait(driver, 20).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR,
                                                                    "div.s-main-slot div[data-component-type='s-search-result'], div.s-result-item"))
                                )
                                logging.info(f"Сторінка результатів {page} успішно завантажена")
                                break
                            except TimeoutException:
                                with open(f"results_page_{page}_attempt_{attempt + 1}.html", "w",
                                          encoding="utf-8") as f:
                                    f.write(driver.page_source)
                                if not self.check_captcha(driver):
                                    logging.warning("CAPTCHA виявлено на сторінці результатів, але продовжуємо")
                                    break
                                if attempt < 2:
                                    driver.execute_cdp_cmd("Network.setUserAgentOverride",
                                                           {"userAgent": self.ua.random})
                                    driver.delete_all_cookies()
                                    driver.refresh()
                                    time.sleep(random.uniform(10, 15))
                                    continue
                                raise

                        if self.cancelled:
                            raise Exception("Скрапінг скасовано")

                        self.human_scroll(driver)
                        self.human_mouse_movement(driver)
                        self.random_interaction(driver)
                        time.sleep(random.uniform(10, 15))

                        soup = BeautifulSoup(driver.page_source, "html.parser")
                        products = soup.select(
                            "div.s-main-slot div[data-component-type='s-search-result'], div.s-result-item")

                        for product in products:
                            if self.cancelled:
                                raise Exception("Скрапінг скасовано")
                            asin = product.get("data-asin")
                            if not asin or not product.select_one("h2"):
                                logging.debug(f"Пропущено продукт без ASIN або заголовка")
                                continue

                            url_elem = product.select_one("a.a-link-normal.s-no-outline")
                            url = "https://www.amazon.com" + url_elem['href'].split("?")[0] if url_elem and url_elem.get("href") else "N/A"
                            if "sspa/click" in url:
                                logging.debug(f"Пропущено спонсорований продукт: {url}")
                                continue

                            logging.info(f"Спарсено URL продукту: {url}")
                            product_data = {
                                "title": get_title_from_soup(product),
                                "price": get_price_from_soup(product),
                                "original_price": get_original_price_from_soup(product),
                                "rating": get_rating_from_soup(product),
                                "reviews": get_reviews_from_soup(product),
                                "seller": get_seller_from_soup(product),
                                "delivery": get_delivery_from_soup(product)
                            }

                            if url != "N/A":
                                product_data.update(self.parse_product_page(driver, url, retries=3))
                                time.sleep(random.uniform(10, 15))

                            if asin:
                                save_to_db({
                                    "asin": asin,
                                    "title": product_data['title'],
                                    "price": product_data['price'],
                                    "original_price": product_data['original_price'],
                                    "rating": product_data['rating'],
                                    "reviews": product_data['reviews'],
                                    "delivery": product_data['delivery'],
                                    "seller": product_data['seller'],
                                    "url": url
                                }, self.db_path)

                                self.total_products += 1
                                logging.info(f"Збережено продукт в базу даних: ASIN={asin}, URL={url}")
                                if task_id:
                                    update_progress()

                        if page < self.pages:
                            if self.cancelled:
                                raise Exception("Скрапінг скасовано")
                            try:
                                next_btn_selectors = [
                                    "a.s-pagination-item.s-pagination-next.s-pagination-button",
                                    "span.a-list-item a[aria-label*='Go to next page']",
                                    "li.s-list-item-margin-right-adjustment a.s-pagination-next",
                                    "a.s-pagination-next"
                                ]
                                next_btn = None
                                for selector in next_btn_selectors:
                                    try:
                                        next_btn = WebDriverWait(driver, 10).until(
                                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                                        )
                                        break
                                    except:
                                        continue

                                if next_btn:
                                    driver.execute_cdp_cmd("Network.setUserAgentOverride",
                                                           {"userAgent": self.ua.random})
                                    driver.delete_all_cookies()
                                    actions = ActionChains(driver)
                                    actions.move_to_element(next_btn).pause(random.uniform(0.7, 1.5)).click().perform()
                                    logging.info(f"Перехід до наступної сторінки {page + 1}")
                                    time.sleep(random.uniform(10, 15))
                                else:
                                    logging.info("Кнопка 'Наступна сторінка' не знайдена, завершуємо перегляд сторінок")
                                    break
                            except:
                                logging.error("Помилка переходу до наступної сторінки")
                                break

                    logging.info("Скрапінг завершено успішно")
                    check_db_contents(self.db_path)
                    return

            except Exception as e:
                logging.error(f"Помилка скрапінгу (спроба {retry + 1}): {e}")
                if retry < max_retries - 1:
                    logging.info(f"Перезапуск скрапінгу (спроба {retry + 2}/{max_retries})")
                    self.cancelled = False
                    time.sleep(random.uniform(15, 20))
                    continue
                logging.error("Досягнуто максимальну кількість спроб. Скрапінг зупинено.")
                raise

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Скрапер Amazon з імітацією людської поведінки")
    parser.add_argument("--query", default="laptop", help="Пошуковий запит (за замовчуванням: laptop)")
    parser.add_argument("--pages", type=int, default=1, help="Кількість сторінок для скрапінгу (за замовчуванням: 1)")
    parser.add_argument("--db", default="amazon.db", help="Шлях до бази даних (за замовчуванням: amazon.db)")
    parser.add_argument("--headless", action="store_true", default=True,
                        help="Запуск у headless-режимі (за замовчуванням: True)")

    args = parser.parse_args()
    if args.pages < 1:
        raise ValueError("Кількість сторінок має бути більшою за 0")

    scraper = AmazonScraper(args.query, args.pages, args.db, headless=args.headless)
    scraper.run()