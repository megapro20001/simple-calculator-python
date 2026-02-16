def read_number(prompt: str) -> float:
    while True:
        raw_value = input(prompt).strip().replace(",", ".")
        try:
            return float(raw_value)
        except ValueError:
            print("Ошибка: введите число (например 12, 3.5, -7).")


def calculate(num1: float, num2: float, operation: str):
    if operation == "+":
        return num1 + num2
    if operation == "-":
        return num1 - num2
    if operation == "*":
        return num1 * num2
    if operation == "/":
        if num2 == 0:
            return "Ошибка: деление на ноль"
        return num1 / num2
    return "Ошибка: неверная операция"


def format_result(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


print("Привет, ты попал в калькулятор 1.1")

num1 = read_number("Введите первое число: ")
num2 = read_number("Введите второе число: ")

print("Выберите операцию: +, -, *, /")
operation = input("Операция: ").strip()

result = calculate(num1, num2, operation)
print("Результат:", format_result(result))
