print("привет ты попал в калькулятор")

num1 = int(input("введите первое число: "))

num2 = int(input("введите второе число: "))

print("выберите операцию: +, -, *, /") 

operation = input("операция: ")

if operation == "+":
    result = num1 + num2
elif operation == "-":
    result = num1 - num2
elif operation == "*":
    result = num1 * num2
elif operation == "/":
    if num2 != 0:
        result = num1 / num2
    else:
        result = "Ошибка: деление на ноль"
else:
    result = "Ошибка: неверная операция"

print("Результат:", result)
 
