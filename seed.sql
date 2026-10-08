INSERT OR IGNORE INTO categories (name, monthly_limit, is_active) VALUES
('Продукты', 25000, 1),
('Бензин', 7000, 1),
('Питомцы', 6000, 1),
('Дом и быт', 5000, 1),
('Развлечения и кафе', 4000, 1),
('Личные покупки', 4000, 1),
('Здоровье', 3000, 1),
('Подарки и праздники', 2000, 1),
('Непредвиденные', 4000, 1);

INSERT OR IGNORE INTO debts (name, planned_amount, is_active) VALUES
('Кредитная карта', 18000, 1),
('Кредит на машину', 30000, 1),
('Ипотека', 9000, 1);

INSERT OR IGNORE INTO income_plans
(day_of_month, name, planned_amount, is_active)
VALUES
(10, 'Зарплата мужа', 50000, 1),
(15, 'Зарплата пользователя', 27500, 1),
(25, 'Аванс мужа', 45000, 1),
(30, 'Аванс пользователя', 27500, 1);
