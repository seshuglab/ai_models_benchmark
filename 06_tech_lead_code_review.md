# Технический руководитель под огнём: принять проект, найти дефекты и поставить задачу

Ты - технический руководитель проекта. Под тобой будут работать другие coding-agent'ы.

Тебе передают небольшой, но уже работающий Python-проект после нескольких итераций разработки. Проект не сломан полностью: обычные сценарии в нём работают, часть проверок проходит, структура в целом понятна. Но внутри накопились реальные дефекты разного уровня: ошибки продуктовой логики, нарушение сохранности данных, неверное использование существующих функций, дублирование, скрытые побочные эффекты, переусложнение и спорные архитектурные решения.

Твоя задача - НЕ чинить проект самостоятельно.

Твоя задача - принять его как технический руководитель:

1. создать проект из файлов ниже в текущей рабочей директории;
2. внимательно изучить все файлы и PRODUCT_RULES.md;
3. понять, как программа работает фактически и как она должна работать по продуктовым правилам;
4. запускать программу и verify.py, если это помогает анализу;
5. найти реальные проблемы, а не максимальное количество замечаний;
6. отличить симптом от корневой причины;
7. оценить приоритет и риск каждой проблемы;
8. принять техническое решение, КАК именно проблему следует исправить;
9. подготовить техническое руководство для другого coding-agent'а, который будет выполнять исправления;
10. выдать весь итог ТОЛЬКО явным ответом в чат.

Это тест роли TECH LEAD / REVIEWER, а не исполнителя.

---

# ЭТАП 1. СОЗДАЙ ПРОЕКТ

Работай только в текущей директории.

Создай ровно эти исходные файлы:

- `app.py`
- `storage.py`
- `catalog.py`
- `discounts.py`
- `orders.py`
- `reporting.py`
- `verify.py`
- `PRODUCT_RULES.md`

Содержимое должно соответствовать тексту ниже.

После того как все 8 файлов созданы, считай их исходной версией проекта.

До завершения анализа и полной подготовки выводов и технического задания НЕ удаляй созданные файлы проекта. Очистка разрешена только на финальном этапе, когда все материалы для ответа уже подготовлены.

После этого:

- НЕ исправляй исходники;
- НЕ меняй `verify.py`;
- НЕ меняй `PRODUCT_RULES.md`;
- НЕ создавай дополнительные исходники, тесты, отчёты, markdown-файлы или временные скрипты;
- НЕ создавай файлы в системном Temp;
- НЕ используй git;
- НЕ читай родительские или соседние директории;
- НЕ ищи внешние инструкции вроде AGENTS.md вне текущей директории;
- НЕ используй интернет.

Разрешено создавать только runtime JSON-файлы, которые сама программа или `verify.py` создают во время запуска.

---

## `storage.py`

```python
import json
from pathlib import Path

BASE_DIR = Path(".")
PRODUCTS_FILE = BASE_DIR / "products.json"
ORDERS_FILE = BASE_DIR / "orders.json"


def load_json(path, default):
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        print(f"Warning: {path.name} is corrupted; using empty data.")
        return default


def save_json(path, data):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

---

## `catalog.py`

```python
from storage import PRODUCTS_FILE, load_json, save_json


def load_products():
    return load_json(PRODUCTS_FILE, [])


def save_products(products):
    save_json(PRODUCTS_FILE, products)


def get_product(products, product_id):
    for product in products:
        if product["id"] == product_id:
            return product
    return None


def reserve_stock(products, lines):
    for line in lines:
        product = get_product(products, line["product_id"])

        if product is None:
            return False, f"Unknown product: {line['product_id']}"

        qty = line["qty"]

        if qty <= 0:
            return False, "Quantity must be positive"

        if not product["active"]:
            return False, f"Product is inactive: {product['id']}"

        if product["stock"] <= qty:
            return False, f"Not enough stock for {product['id']}"

        product["stock"] -= qty
        save_products(products)

    return True, ""


def restore_stock(products, lines):
    for line in lines:
        product = get_product(products, line["product_id"])
        if product is not None:
            product["stock"] += line["qty"]
```

---

## `discounts.py`

```python
class DiscountRule:
    def discount_cents(self, subtotal_cents):
        raise NotImplementedError


class NoDiscount(DiscountRule):
    def discount_cents(self, subtotal_cents):
        return 0


class Save10Discount(DiscountRule):
    MIN_SUBTOTAL_CENTS = 2000

    def discount_cents(self, subtotal_cents):
        if subtotal_cents < self.MIN_SUBTOTAL_CENTS:
            return 0
        return subtotal_cents // 10


class DiscountRuleFactory:
    def create(self, code):
        if code == "":
            return NoDiscount()
        if code == "SAVE10":
            return Save10Discount()
        raise ValueError(f"Unknown discount code: {code}")


def discount_cents(subtotal_cents, code):
    rule = DiscountRuleFactory().create(code)
    return rule.discount_cents(subtotal_cents)
```

---

## `orders.py`

```python
from datetime import datetime

from catalog import (
    get_product,
    load_products,
    reserve_stock,
    restore_stock,
    save_products,
)
from discounts import discount_cents
from storage import ORDERS_FILE, load_json, save_json


def load_orders():
    return load_json(ORDERS_FILE, [])


def save_orders(orders):
    save_json(ORDERS_FILE, orders)


def next_order_id(orders):
    if not orders:
        return 1
    return max(order["id"] for order in orders) + 1


def create_order(lines, discount_code=""):
    products = load_products()
    orders = load_orders()

    ok, error = reserve_stock(products, lines)
    if not ok:
        return None, error

    subtotal_cents = 0
    order_lines = []

    for line in lines:
        product = get_product(products, line["product_id"])
        line_total_cents = product["price_cents"] * line["qty"]
        subtotal_cents += line_total_cents

        order_lines.append(
            {
                "product_id": product["id"],
                "name": product["name"],
                "qty": line["qty"],
                "unit_price_cents": product["price_cents"],
                "line_total_cents": line_total_cents,
            }
        )

    discount_value_cents = 0
    if discount_code == "SAVE10":
        discount_value_cents = subtotal_cents // 10

    order = {
        "id": next_order_id(orders),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "new",
        "discount_code": discount_code,
        "subtotal_cents": subtotal_cents,
        "discount_cents": discount_value_cents,
        "total_cents": subtotal_cents - discount_value_cents,
        "lines": order_lines,
    }

    save_products(products)
    orders.append(order)
    save_orders(orders)

    return order, ""


def cancel_order(order_id):
    products = load_products()
    orders = load_orders()

    order = next((item for item in orders if item["id"] == order_id), None)

    if order is None:
        return False, "Order not found"

    restore_stock(products, order["lines"])
    order["status"] = "cancelled"

    save_products(products)
    save_orders(orders)

    return True, ""


def delete_cancelled_order(order_id):
    orders = load_orders()

    for index, order in enumerate(orders):
        if order["id"] == order_id:
            if order["status"] != "cancelled":
                return False, "Only cancelled orders can be deleted"

            del orders[index]
            save_orders(orders)
            return True, ""

    return False, "Order not found"
```

---

## `reporting.py`

```python
from catalog import load_products
from orders import load_orders


def revenue_cents():
    return sum(order["total_cents"] for order in load_orders())


def category_totals_cents():
    products = load_products()
    product_by_id = {product["id"]: product for product in products}
    totals = {}

    for order in load_orders():
        for line in order["lines"]:
            product = product_by_id[line["product_id"]]
            category = product["category"]
            value = product["price_cents"] * line["qty"]
            totals[category] = totals.get(category, 0) + value

    return totals
```

---

## `app.py`

```python
from catalog import load_products, save_products
from orders import (
    cancel_order,
    create_order,
    delete_cancelled_order,
    load_orders,
)
from reporting import category_totals_cents, revenue_cents


def ensure_demo_products():
    if load_products():
        return

    save_products(
        [
            {
                "id": "tea",
                "name": "Tea",
                "category": "food",
                "price_cents": 350,
                "stock": 5,
                "active": True,
            },
            {
                "id": "bread",
                "name": "Bread",
                "category": "food",
                "price_cents": 500,
                "stock": 4,
                "active": True,
            },
            {
                "id": "mug",
                "name": "Mug",
                "category": "home",
                "price_cents": 1500,
                "stock": 2,
                "active": True,
            },
            {
                "id": "poster",
                "name": "Poster",
                "category": "Home",
                "price_cents": 800,
                "stock": 3,
                "active": False,
            },
        ]
    )


def parse_lines(raw):
    lines = []

    for chunk in raw.split(","):
        product_id, qty_text = chunk.split(":", 1)
        lines.append(
            {
                "product_id": product_id.strip(),
                "qty": int(qty_text),
            }
        )

    return lines


def show_products():
    for product in load_products():
        marker = "" if product["active"] else " [inactive]"
        print(
            f"{product['id']}: {product['name']} | "
            f"{product['price_cents'] / 100:.2f} | "
            f"stock={product['stock']}{marker}"
        )


def show_orders():
    for order in load_orders():
        print(
            f"#{order['id']} | {order['status']} | "
            f"{order['total_cents'] / 100:.2f} | "
            f"{order['created_at']}"
        )


def run():
    ensure_demo_products()

    while True:
        print(
            "\n1. Products\n"
            "2. Create order\n"
            "3. Cancel order\n"
            "4. Delete cancelled order\n"
            "5. Orders\n"
            "6. Reports\n"
            "0. Exit"
        )

        choice = input("Choice: ").strip()

        if choice == "0":
            return

        if choice == "1":
            show_products()
            continue

        if choice == "2":
            raw = input("Items (product:qty,product:qty): ").strip()
            code = input("Discount code (optional): ").strip()

            try:
                lines = parse_lines(raw)
            except (ValueError, TypeError):
                print("Invalid item format")
                continue

            order, error = create_order(lines, code)

            if order is None:
                print(f"Order rejected: {error}")
            else:
                print(
                    f"Created order #{order['id']} "
                    f"for {order['total_cents'] / 100:.2f}"
                )
            continue

        if choice == "3":
            try:
                order_id = int(input("Order ID: "))
            except ValueError:
                print("Invalid ID")
                continue

            ok, error = cancel_order(order_id)
            print("Cancelled" if ok else error)
            continue

        if choice == "4":
            try:
                order_id = int(input("Order ID: "))
            except ValueError:
                print("Invalid ID")
                continue

            ok, error = delete_cancelled_order(order_id)
            print("Deleted" if ok else error)
            continue

        if choice == "5":
            show_orders()
            continue

        if choice == "6":
            print(f"Revenue: {revenue_cents() / 100:.2f}")
            for category, value in category_totals_cents().items():
                print(f"{category}: {value / 100:.2f}")
            continue

        print("Unknown command")


if __name__ == "__main__":
    run()
```

---

## `verify.py`

`verify.py` - это полезная, но НЕ полная проверка проекта.

Не считай, что зелёный тест автоматически означает отсутствие других проблем.
Не считай, что каждый FAIL указывает на корневую причину.

```python
import json

from catalog import load_products
from orders import (
    cancel_order,
    create_order,
    delete_cancelled_order,
)
from reporting import category_totals_cents
from storage import ORDERS_FILE, PRODUCTS_FILE


BASE_PRODUCTS = [
    {
        "id": "tea",
        "name": "Tea",
        "category": "food",
        "price_cents": 350,
        "stock": 5,
        "active": True,
    },
    {
        "id": "bread",
        "name": "Bread",
        "category": "food",
        "price_cents": 500,
        "stock": 4,
        "active": True,
    },
    {
        "id": "mug",
        "name": "Mug",
        "category": "home",
        "price_cents": 1500,
        "stock": 2,
        "active": True,
    },
]


def reset_state():
    PRODUCTS_FILE.write_text(
        json.dumps(BASE_PRODUCTS, indent=2),
        encoding="utf-8",
    )
    ORDERS_FILE.write_text("[]", encoding="utf-8")


def stock(product_id):
    return next(
        product["stock"]
        for product in load_products()
        if product["id"] == product_id
    )


def check(name, condition):
    if condition:
        print(f"PASS: {name}")
        return 1, 0

    print(f"FAIL: {name}")
    return 0, 1


def main():
    passed = 0
    failed = 0

    reset_state()
    order, error = create_order([{"product_id": "tea", "qty": 2}])
    p, f = check(
        "basic order is created",
        order is not None and error == "" and order["total_cents"] == 700,
    )
    passed += p
    failed += f

    p, f = check("stock is reduced", stock("tea") == 3)
    passed += p
    failed += f

    reset_state()
    order, error = create_order([{"product_id": "tea", "qty": 0}])
    p, f = check(
        "zero quantity is rejected",
        order is None and stock("tea") == 5,
    )
    passed += p
    failed += f

    reset_state()
    order, error = create_order([{"product_id": "tea", "qty": 2}])
    ok, error = cancel_order(order["id"])
    p, f = check(
        "single cancellation restores stock",
        ok and stock("tea") == 5,
    )
    passed += p
    failed += f

    reset_state()
    create_order([{"product_id": "tea", "qty": 2}])
    p, f = check(
        "basic category report",
        category_totals_cents() == {"food": 700},
    )
    passed += p
    failed += f

    reset_state()
    order, error = create_order([{"product_id": "tea", "qty": 5}])
    p, f = check(
        "buying exact available stock is allowed",
        order is not None and stock("tea") == 0,
    )
    passed += p
    failed += f

    reset_state()
    order, error = create_order(
        [{"product_id": "tea", "qty": 2}],
        "SAVE10",
    )
    p, f = check(
        "SAVE10 is not applied below threshold",
        order is not None and order["total_cents"] == 700,
    )
    passed += p
    failed += f

    reset_state()
    order, error = create_order([{"product_id": "tea", "qty": 2}])
    cancel_order(order["id"])
    second_ok, second_error = cancel_order(order["id"])
    p, f = check(
        "second cancellation changes nothing",
        not second_ok and stock("tea") == 5,
    )
    passed += p
    failed += f

    reset_state()
    first, _ = create_order([{"product_id": "tea", "qty": 1}])
    cancel_order(first["id"])
    delete_cancelled_order(first["id"])
    second, _ = create_order([{"product_id": "tea", "qty": 1}])
    p, f = check(
        "deleted order ID is never reused",
        second is not None and second["id"] == first["id"] + 1,
    )
    passed += p
    failed += f

    print(f"\nSUMMARY: {passed} passed, {failed} failed")


if __name__ == "__main__":
    main()
```

---

## `PRODUCT_RULES.md`

```markdown
# PRODUCT RULES - OrderDesk

Это небольшой локальный консольный продукт для одного оператора.
Цель проекта - простота и предсказуемость, а не масштабирование.

## Хранение

PR-01. `products.json` и `orders.json` должны храниться рядом со скриптами проекта независимо от текущей директории запуска.

PR-02. Если существующий JSON повреждён, программа должна остановить соответствующую операцию с понятной ошибкой. Повреждённый файл нельзя автоматически заменять пустыми данными или перезаписывать.

PR-03. Запись JSON не должна оставлять частично записанный файл при обычной ошибке записи или прерывании процесса. Формат существующих JSON менять нельзя.

## Заказы и склад

PR-04. Количество позиции - положительное целое число от `1` до текущего остатка включительно. Покупка ровно всего доступного остатка разрешена.

PR-05. Неактивный товар заказать нельзя.

PR-06. Создание заказа - одна логическая операция. Если заказ не может быть полностью создан и сохранён, постоянные данные заказа и склада должны остаться такими, какими были до операции.

PR-07. Ошибка в любой позиции заказа не должна частично уменьшать остатки других позиций.

PR-08. Отмена заказа разрешена только один раз. Повторная отмена должна вернуть ошибку и не менять склад.

PR-09. Удалять разрешено только отменённый заказ.

PR-10. ID заказа монотонный и никогда не используется повторно, даже если последний заказ был отменён и удалён.

## Скидки

PR-11. `discounts.discount_cents(subtotal_cents, code)` - единственная функция, определяющая правила скидок. Другие модули не должны дублировать эту логику.

PR-12. Пустой код означает отсутствие скидки. `SAVE10` даёт 10% только при subtotal >= 2000 cents. Ниже порога заказ создаётся без скидки. Неизвестный непустой код должен отклонить заказ без изменения склада или заказов.

## Отчёты

PR-13. Отменённые заказы не входят в выручку и продажи по категориям.

PR-14. Продажи по категориям считаются по сохранённым в заказе `line_total_cents`, а не по текущей цене товара. Это исторический отчёт.

PR-15. Категории регистрозависимы намеренно: `home` и `Home` - разные категории.

## Деньги, интерфейс и область изменений

PR-16. Все денежные значения хранятся целыми центами (`int`). `float`, `Decimal` и валютный слой не нужны.

PR-17. Дата/время заказа создаётся программой. Пользователь не вводит дату вручную.

PR-18. Публичные CLI-команды, формат существующих JSON и сигнатуры существующих публичных функций менять нельзя без необходимости для исправления реального дефекта.

PR-19. Подтверждение перед отменой или удалением не требуется.

PR-20. Поля каталога считаются доверенными данными продукта. Не надо добавлять универсальную schema-validation, классы моделей, ORM, базу данных, dependency injection, plugin system или архитектуру "на будущее".

PR-21. Приоритет продукта: сохранность данных и корректность бизнес-правил, затем локальное упрощение и устранение дублирования. Косметический рефакторинг не должен маскироваться под исправление дефекта.
```

---

# ЭТАП 2. ИССЛЕДУЙ ПРОЕКТ

После создания файлов изучи проект как технический руководитель.

Обязательно:

1. Прочитай `PRODUCT_RULES.md` целиком.
2. Прочитай все исходные `.py`-файлы.
3. Проследи зависимости между модулями и состояние данных.
4. Запусти:

```text
python verify.py
```

5. При необходимости запусти отдельные существующие функции или `app.py`, но НЕ создавай для этого новые скрипты и НЕ изменяй проект.
6. Не ограничивай анализ тем, что проверяет `verify.py`.
7. Не считай каждый FAIL отдельной корневой причиной: один дефект может давать несколько симптомов.
8. Не считай необычный код ошибкой, если он соответствует PRODUCT_RULES.

Проверяй как минимум следующие классы проблем:

- продуктовая логика;
- сохранность данных;
- атомарность операций;
- порядок изменения состояния;
- обработка ошибок;
- скрытые побочные эффекты;
- дублирование логики;
- использование уже существующих функций не по назначению или обход их;
- некорректные границы ответственности функций;
- KISS/YAGNI;
- переусложнение;
- спагетти-код;
- ошибки отчётности;
- устойчивость решений между несколькими запусками программы;
- неверные предположения о текущей директории и файлах.

---

# ЭТАП 3. НЕ ИСПРАВЛЯЙ КОД

После начала анализа исходники считаются READ ONLY.

Ты НЕ исполнитель.

Нельзя:

- исправлять `.py`;
- исправлять PRODUCT_RULES;
- исправлять verify.py;
- добавлять тесты;
- добавлять новые модули;
- создавать `REPORT.md`, `TASK.md`, `TODO.md` и любые другие файлы с результатом;
- выдавать полностью переписанные версии существующих файлов;
- начинать рефакторинг только потому, что код можно сделать красивее.

Можно показывать в финальном ответе небольшие фрагменты кода или псевдокод, если они помогают объяснить рекомендуемое исправление.

---

# ЭТАП 4. ПРИМИ ТЕХНИЧЕСКИЕ РЕШЕНИЯ

Для каждой найденной реальной проблемы недостаточно написать:

- "исправить атомарность";
- "убрать дублирование";
- "отрефакторить функцию";
- "сделать код чище".

Ты обязан объяснить ДРУГОМУ АГЕНТУ, КАК предлагаешь её исправить.

Если есть несколько разумных вариантов:

- выбери один рекомендуемый;
- объясни, почему он подходит именно этому проекту;
- предпочитай минимальное локальное изменение;
- учитывай KISS/YAGNI;
- не перечисляй архитектурные варианты ради полноты;
- не перекладывай ключевое архитектурное решение на исполнителя.

Хорошее решение должно по возможности сохранять:

- публичные функции;
- CLI;
- JSON-формат;
- продуктовые правила;
- существующую простую архитектуру.

Но не сохраняй плохую архитектуру только ради минимального diff, если она непосредственно создаёт риск потери данных или повторяющиеся дефекты.

---

# ЭТАП 5. ФИНАЛЬНЫЙ ОТВЕТ - ТОЛЬКО В ЧАТ

Никаких файлов с результатом.

Финальный ответ должен быть самостоятельным техническим документом, который можно передать следующему coding-agent'у.

Используй следующую структуру.

## 1. ИТОГОВАЯ ОЦЕНКА ПРОЕКТА

Кратко:

- насколько проект работоспособен сейчас;
- можно ли безопасно продолжать разработку без исправлений;
- какие 2–4 риска самые серьёзные;
- что является главной проблемой: локальные баги, сохранность данных, архитектура, дисциплина бизнес-правил или сочетание факторов.

Не начинай с пересказа всех файлов.

---

## 2. КАРТА ПРОБЛЕМ

Дай компактную таблицу:

| ID | Приоритет | Файл / функция | Краткая проблема | Нарушенное правило | Root cause или symptom |

Используй приоритеты:

- `P0` - риск потери/повреждения данных или критическая несогласованность;
- `P1` - серьёзная ошибка продуктовой логики;
- `P2` - архитектурная/поддерживаемостная проблема, уже создающая риск ошибок;
- `P3` - локальное качество кода без немедленного продуктового риска.

Не раздувай список искусственно.

Если несколько симптомов имеют одну корневую причину, сгруппируй их.

---

## 3. ПОДРОБНОЕ РЕВЬЮ

Для КАЖДОЙ проблемы укажи:

### `[ID] Название`

**Приоритет:** P0/P1/P2/P3

**Где:** конкретный файл, функция и по возможности участок логики.

**Что происходит:** наблюдаемый дефект или риск.

**Почему это реальная проблема:** чем она отличается от вкусового замечания.

**Корневая причина:** не повторяй симптом другими словами.

**Нарушенное продуктовое правило:** PR-XX. Если продуктовые правила не нарушены напрямую - так и напиши.

**Рекомендуемое решение:** какое решение ты как руководитель выбираешь.

**Как именно исправить:** пошаговое техническое направление для coding-agent'а. Здесь должно быть достаточно информации, чтобы исполнитель не принимал заново ключевое архитектурное решение.

**Что НЕ менять:** границы исправления, публичные интерфейсы, данные или соседний код, который не должен попасть под рефакторинг.

**Acceptance criteria:** конкретный результат после исправления.

**Как проверить:** существующая проверка, новый сценарий, fault injection или ручной сценарий, который исполнитель должен реализовать/запустить после правки.

**Зависимости:** какие исправления нужно сделать раньше или вместе с этим.

Если проблема не требует отдельного изменения, а является следствием другой - не создавай искусственную задачу, а свяжи её с root cause.

---

## 4. ПОРЯДОК ВЫПОЛНЕНИЯ РАБОТ

Расставь найденные исправления в порядке реализации.

Приоритет порядка:

1. сохранность данных;
2. атомарность и согласованность состояния;
3. ошибки бизнес-логики;
4. неправильное использование общих функций и дублирование правил;
5. архитектурное упрощение, если оно реально снижает риск;
6. косметические замечания - только если вообще нужны.

Для каждого этапа коротко объясни, почему он стоит именно здесь.

Учитывай зависимости: не проси исполнителя сначала делать рефакторинг кода, который следующее исправление всё равно существенно изменит.

---

## 5. ТЕХНИЧЕСКОЕ ЗАДАНИЕ АГЕНТУ-ИСПОЛНИТЕЛЮ

Теперь преврати ревью в конкретное рабочее ТЗ.

Оно должно содержать:

- цель работы;
- список задач в порядке выполнения;
- для каждой задачи - краткое техническое направление КАК исправлять;
- файлы, которые разрешено менять;
- файлы/интерфейсы/форматы, которые нельзя менять;
- критерии приёмки;
- проверки после каждого важного этапа;
- финальную регрессионную проверку.

Не пиши исполнителю просто "найди решение" там, где решение уже должен принять технический руководитель.

Одновременно не диктуй несущественные детали вроде имён локальных переменных, если они не влияют на архитектуру или продукт.

---

## 6. ЧТО СОЗНАТЕЛЬНО НЕ НАДО ИСПРАВЛЯТЬ

Перечисли заметные места, которые могут выглядеть подозрительно, но по PRODUCT_RULES являются допустимыми или не стоят изменения сейчас.

Этот раздел обязателен.

Особенно проверь, не пытаешься ли ты без требования:

- сделать категории case-insensitive;
- добавить Decimal;
- добавить ORM/DB;
- добавить классы моделей;
- добавить DI/framework;
- добавить подтверждение удаления;
- добавить ручной ввод даты;
- универсально валидировать доверенный каталог;
- менять JSON-schema;
- переписывать CLI;
- делать "архитектуру на будущее".

---

## 7. НЕУВЕРЕННОСТИ И ДОПУЩЕНИЯ

Если какое-то замечание нельзя доказать из кода, PRODUCT_RULES или воспроизводимого поведения:

- не выдавай его за установленный баг;
- обозначь как риск / гипотезу;
- укажи, какой проверкой это подтвердить.

Если всё доказано - напиши, что существенных неопределённостей не осталось.

---

## 8. ОЧИСТКА

В финальном ответе обязательно укажи:

- что было удалено после завершения анализа;
- какие runtime-файлы и каталоги появились во время работы;
- результат финальной проверки текущей директории.

Финальная директория должна быть полностью пустой.

---

# ЭТАП 6. ФИНАЛЬНАЯ ОЧИСТКА

Этот этап выполняется ТОЛЬКО после того, как:

- анализ проекта завершён;
- все найденные проблемы и решения уже определены;
- порядок работ составлен;
- техническое задание агенту-исполнителю полностью подготовлено;
- все данные, необходимые для финального ответа в чат, сохранены в контексте.

После этого удали ВСЁ, что было создано в текущей рабочей директории во время теста, включая:

- все 8 исходных файлов проекта;
- `products.json` и `orders.json`, если они появились;
- любые другие runtime JSON-файлы;
- временные файлы, созданные программой во время запуска;
- `__pycache__`;
- все `.pyc`;
- любые другие файлы или каталоги, появившиеся в текущей директории во время теста.

Правила очистки:

- НЕ удаляй и НЕ изменяй ничего за пределами текущей рабочей директории;
- НЕ создавай отдельные cleanup-скрипты;
- НЕ используй `PYTHONDONTWRITEBYTECODE` и другие способы искусственно предотвращать обычное создание bytecode или runtime-файлов;
- если программа создала обычные временные/runtime-файлы, удали их именно на этом этапе;
- после удаления обязательно проверь содержимое текущей директории;
- текущая директория должна быть полностью пустой;
- после финальной проверки директории ничего больше не создавай.

Только после успешной очистки отправляй подготовленный финальный ответ в чат.

В разделе `8. ОЧИСТКА` финального ответа покажи:

- что именно было удалено;
- какие автоматически созданные файлы/каталоги были обнаружены;
- чем проверена директория после удаления;
- подтверждение, что после проверки директория пуста.

---

# КРИТЕРИИ ХОРОШЕГО РУКОВОДИТЕЛЯ

В этом тесте оценивается не длина ответа и не количество найденных замечаний.

Хороший результат показывает, что агент:

- понял проект целиком, а не отдельные функции;
- сверял код с продуктовыми правилами;
- нашёл проблемы, которых нет в verify.py;
- не ограничился FAIL-ами verify.py;
- отличил симптомы от root cause;
- заметил риски сохранности и атомарности;
- увидел неправильное дублирование продуктовой логики;
- заметил переусложнение, но не сделал его главным приоритетом;
- не придумал лишние требования;
- умеет сказать "это не надо менять";
- расставил исправления в разумном порядке;
- выбрал конкретные технические решения;
- объяснил другому агенту КАК исправлять;
- не начал сам реализовывать исправления;
- не вышел за пределы рабочей директории;
- после завершения анализа полностью очистил текущую директорию и подтвердил, что она пуста;
- выдал весь итог явно в чат.

Твоя конечная роль здесь - не самый быстрый программист.

Твоя роль - технический руководитель, после решения которого другой агент должен суметь безопасно исправить проект, не принимая заново ключевые продуктовые и архитектурные решения.
