from aiogram import Router
from aiogram.types import Message

from app.budget import (
    add_income,
    check_expense,
    get_monthly_report,
    save_expense,
)
from app.keyboards import (
    main_menu,
)
from app.payment_flow import (
    get_current_balance,
    get_event_summary,
    record_actual_income,
    record_actual_payment,
    start_early_income_event,
    start_income_event,
)
from app.payments import (
    get_event,
    get_event_payments,
)
from app.allocation import (
    calculate_remaining_monthly_budgets,
    get_monthly_budget_summary,
)


router = Router()


@router.message(
    lambda message: message.text == "📅 Отчёт за месяц"
)
async def monthly_report_button(
    message: Message,
):
    report = await get_monthly_report()

    month = report["month"]

    lines = [
        f"📅 Отчёт за {month}",
        "",
        "💰 ДОХОДЫ",
        f"За месяц: "
        f"{report['month_income']:,.0f} ₽",
        "",
        "🏦 ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ",
        f"💳 Кредиты: "
        f"{report['credit_expenses']:,.0f} ₽",
        f"🏠 Ипотека: "
        f"{report['mortgage_expenses']:,.0f} ₽",
        f"🧾 Коммуналка: "
        f"{report['utilities_expenses']:,.0f} ₽",
        "────────────────",
        f"Всего: "
        f"{report['mandatory_expenses']:,.0f} ₽",
        "",
        "🛒 РАСХОДЫ НА ЖИЗНЬ",
        f"Бюджет: "
        f"{report['life_budget']:,.0f} ₽",
        f"Потрачено: "
        f"{report['life_expenses']:,.0f} ₽",
        f"Осталось: "
        f"{report['life_remaining']:,.0f} ₽",
        "",
        "📊 ПО КАТЕГОРИЯМ",
    ]

    for category in report["categories"]:
        lines.extend(
            [
                "",
                f"• {category['name']}",
                f"  Лимит: "
                f"{category['limit']:,.0f} ₽",
                f"  Потрачено: "
                f"{category['spent']:,.0f} ₽",
                f"  Осталось: "
                f"{category['remaining']:,.0f} ₽",
            ]
        )

    lines.extend(
        [
            "",
            "📦 РАСПРЕДЕЛЕНИЕ",
            f"Распределено по категориям: "
            f"{report['category_allocations']:,.0f} ₽",
            f"Осталось распределить: "
            f"{report['life_remaining_to_allocate']:,.0f} ₽",
            "",
            "🐷 НАКОПЛЕНИЯ",
            f"Отложено в этом месяце: "
            f"{report['monthly_savings']:,.0f} ₽",
            f"Цель месяца: "
            f"{report['savings_target']:,.0f} ₽",
            f"До цели осталось: "
            f"{report['savings_remaining']:,.0f} ₽",
            f"Всего в копилке: "
            f"{report['savings_balance']:,.0f} ₽",
            "",
            "💳 ДЕНЬГИ",
            f"Основной счёт: "
            f"{report['main_account']:,.0f} ₽",
            f"Свободно сверх текущих целей: "
            f"{report['free_after_targets']:,.0f} ₽",
        ]
    )

    await message.answer(
        "\n".join(lines).replace(",", " "),
        reply_markup=main_menu(),
    )
