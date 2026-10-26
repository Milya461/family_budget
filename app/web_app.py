WEB_APP_HTML = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#e4e4e1">
<meta name="description" content="Семейный бюджет: реальные остатки, расходы, обязательные платежи и копилка.">
<title>Семейный бюджет — панель управления</title>
<style>
:root{--paper:#e4e4e1;--panel:#eaeae7;--ink:#101010;--muted:#666660;--line:rgba(10,10,10,.23);--softline:rgba(10,10,10,.12);--white:#f5f5f2;--accent:#b7c8c1;--radius:0px;--shadow:none}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.45}
button,input,select,textarea{font:inherit;color:inherit}
button{cursor:pointer}
a{color:inherit}
.shell{width:min(1200px,100%);margin:0 auto;padding:0 26px}
body{padding-bottom:calc(96px + env(safe-area-inset-bottom))}
.app-view{display:none;min-height:52vh}
.app-view.active{display:block}
.app-view.active .section-heading:first-child{padding-top:24px}
.home-shortcuts{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:25px 0 14px;border-bottom:1px solid var(--line)}
.home-shortcut-copy{flex:1 1 100%;padding-bottom:8px}
.home-shortcut-copy h2{font-size:clamp(22px,4vw,34px);line-height:1;margin:11px 0 7px;letter-spacing:-.06em;text-transform:uppercase}
.home-shortcut-copy p{margin:0;font-size:11px;color:var(--muted)}
.home-shortcuts .pill{font:inherit;font-size:10px}
.category-only{padding-bottom:10px}
.category-only>.category-list{margin-top:4px}
.savings-layout,.balance-layout{width:min(740px,100%);padding:22px 0}
.savings-layout .line-card,.balance-layout .line-card{width:100%;max-width:620px}
.savings-layout .line-card h3,.balance-layout .line-card h3{font-size:18px}
.operation-forms{grid-template-columns:repeat(2,minmax(0,1fr));gap:26px}
.operation-forms .action-card{padding:22px 20px 24px 0;margin:0}
.operation-forms .action-card:nth-child(2){border-right:0}
.operation-forms .action-number{font-size:42px}
#view-more #history{margin-top:8px}
.bottom-nav{position:fixed;z-index:35;left:50%;transform:translateX(-50%);bottom:0;width:min(720px,100%);display:grid;grid-template-columns:repeat(6,minmax(0,1fr));padding:8px 8px calc(8px + env(safe-area-inset-bottom));background:rgba(228,228,225,.97);border:1px solid var(--line);border-bottom:0;box-shadow:0 -7px 26px rgba(0,0,0,.06);backdrop-filter:blur(12px)}
.bottom-nav button{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-height:55px;padding:7px 3px 5px;border:0;border-top:2px solid transparent;background:transparent;color:var(--muted);font-size:9px;letter-spacing:.01em}
.bottom-nav button .tab-icon{font-size:17px;line-height:1;color:var(--ink);font-weight:600}
.bottom-nav button .tab-label{white-space:nowrap}
.bottom-nav button.active{border-top-color:var(--ink);background:rgba(255,255,255,.35);color:var(--ink);font-weight:700}
.bottom-nav button:focus-visible{outline:2px solid var(--ink);outline-offset:-2px}
#view-more .table-wrap{margin-bottom:18px}
#view-more .section-heading{scroll-margin-top:15px}

.topbar{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:22px 0;border-bottom:1px solid var(--line)}
.brand{font-size:14px;font-weight:900;letter-spacing:.04em;line-height:1.1}
.brand small{display:block;margin-top:5px;font-size:9px;font-weight:500;letter-spacing:.16em}
.nav{display:flex;align-items:center;gap:22px;flex-wrap:wrap}
.nav a{text-decoration:none;font-size:10px;text-transform:uppercase;letter-spacing:.12em}
.nav a:hover{text-decoration:underline;text-underline-offset:5px}
.nav .logout{border:1px solid var(--ink);background:transparent;padding:8px 12px;font-size:10px}
.hero{position:relative;min-height:350px;padding:46px 0 25px;overflow:hidden;border-bottom:1px solid var(--line)}
.eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.18em}
.hero h1{position:relative;z-index:1;max-width:650px;margin:26px 0 18px;font-size:clamp(44px,8vw,100px);line-height:.88;letter-spacing:-.085em;font-weight:900;text-transform:uppercase}
.hero h1 span{display:block;font-weight:400;letter-spacing:-.075em}
.hero-bottom{display:flex;justify-content:space-between;align-items:end;gap:24px;position:relative;z-index:1}
.hero-bottom p{max-width:400px;margin:0;color:#454540;font-size:12px}
.wave{position:absolute;right:-3%;top:4px;width:66%;height:300px;opacity:.9;pointer-events:none}
.pill{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--ink);border-radius:30px;padding:10px 16px;background:transparent;font-size:10px;text-transform:uppercase;letter-spacing:.06em;white-space:nowrap}
.pill:hover,.button:hover{background:var(--ink);color:var(--paper)}
.pill.primary,.button.primary{background:var(--ink);color:var(--paper)}
.pill.primary:hover,.button.primary:hover{background:#393936}
.section-heading{display:flex;justify-content:space-between;align-items:end;gap:18px;padding:27px 0 13px;border-bottom:1px solid var(--line)}
.section-heading h2{margin:0;font-size:21px;line-height:1;text-transform:uppercase;letter-spacing:-.05em}
.section-heading p{margin:5px 0 0;color:var(--muted);font-size:11px}
.month-control{display:flex;align-items:center;gap:8px}
.month-control input{width:130px}
input,select,textarea{width:100%;min-width:0;padding:12px 12px;border:1px solid var(--line);background:rgba(255,255,255,.22);border-radius:0;outline:none}
input:focus,select:focus,textarea:focus{border-color:#000;background:rgba(255,255,255,.55)}
label{display:block;margin:0 0 6px;font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#4a4a46}
.form-field{min-width:0}
.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.form-grid .wide{grid-column:1/-1}
.button{border:1px solid var(--ink);background:transparent;padding:11px 14px;font-size:10px;text-transform:uppercase;letter-spacing:.08em}
.button:disabled{opacity:.4;cursor:not-allowed}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:1px solid var(--line)}
.stat{padding:22px 20px 23px 0;border-right:1px solid var(--line);margin-right:20px;min-width:0}
.stat:last-child{border-right:0;margin-right:0}
.stat .label{font-size:9px;text-transform:uppercase;letter-spacing:.13em;color:var(--muted)}
.stat .value{font-size:clamp(24px,3vw,39px);font-weight:800;letter-spacing:-.07em;margin:10px 0 3px;white-space:nowrap}
.stat .note{font-size:10px;color:var(--muted)}
.content-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(300px,.85fr);gap:28px;padding:0 0 20px}
.category-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
.category{border-bottom:1px solid var(--line);padding:17px 18px 16px 0;min-width:0}
.category:nth-child(odd){padding-right:18px;border-right:1px solid var(--softline)}
.category:nth-child(even){padding-left:18px}
.category-top{display:flex;justify-content:space-between;gap:10px;align-items:start}
.category-name{font-weight:700;font-size:13px}
.category-amount{font-size:12px;font-weight:700;white-space:nowrap}
.category-meta{display:flex;justify-content:space-between;gap:8px;margin:12px 0 7px;font-size:10px;color:var(--muted)}
.track{height:3px;background:rgba(0,0,0,.12);overflow:hidden}
.track span{display:block;height:100%;background:#111;max-width:100%}
.side-stack{display:grid;align-content:start;gap:20px}
.line-card{border:1px solid var(--line);padding:18px}
.line-card h3{margin:0 0 7px;font-size:14px;letter-spacing:-.03em;text-transform:uppercase}
.line-card .sub{margin:0 0 17px;font-size:11px;color:var(--muted)}
.metric-line{display:flex;justify-content:space-between;align-items:baseline;gap:12px;border-top:1px solid var(--softline);padding:10px 0;font-size:11px}
.metric-line strong{font-size:13px}
.action-layout{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;border-bottom:1px solid var(--line)}
.action-card{padding:20px 18px 22px 0;border-right:1px solid var(--line);margin-right:18px;min-width:0}
.action-card:last-child{border-right:0;margin-right:0}
.action-number{font-size:33px;line-height:1;letter-spacing:-.07em;margin-bottom:15px;font-weight:500}
.action-card h3{margin:0 0 8px;font-size:13px;text-transform:uppercase;letter-spacing:-.02em}
.action-card p{min-height:30px;margin:0 0 15px;color:var(--muted);font-size:10px}
.action-card .button{width:100%}
.payment-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 20px}
.payment-item{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:15px 0;border-bottom:1px solid var(--line)}
.payment-item h4{margin:0 0 3px;font-size:12px}
.payment-item p{margin:0;font-size:10px;color:var(--muted)}
.status{display:inline-flex;border:1px solid var(--line);padding:4px 7px;font-size:9px;text-transform:uppercase;white-space:nowrap}
.status.paid{border-color:#677f72;color:#355c49}
.table-wrap{overflow:auto;border-bottom:1px solid var(--line)}
table{border-collapse:collapse;width:100%;min-width:610px;text-align:left}
th{padding:12px 10px 12px 0;font-size:9px;font-weight:500;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);border-bottom:1px solid var(--line)}
td{padding:13px 10px 13px 0;border-bottom:1px solid var(--softline);font-size:11px;vertical-align:top}
tbody tr:last-child td{border-bottom:0}
.right{text-align:right}
.type{font-size:9px;text-transform:uppercase;color:var(--muted)}
.positive{color:#264e3b}.negative{color:#6b3833}
.empty{padding:22px 0;color:var(--muted);font-size:11px}
.footer-wave{position:relative;margin-top:30px;min-height:155px;overflow:hidden;border-top:1px solid var(--line)}
.footer-wave svg{width:100%;height:170px;display:block}
.footer{display:flex;justify-content:space-between;gap:20px;align-items:center;padding:17px 0 30px;font-size:9px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted)}
.toast{position:fixed;right:20px;bottom:20px;z-index:30;max-width:calc(100% - 40px);width:360px;background:#111;color:#f5f5f2;padding:14px 16px;font-size:12px;display:none;box-shadow:0 5px 20px rgba(0,0,0,.12)}
.toast.show{display:block}
.loading{opacity:.5;pointer-events:none}
.overlay{position:fixed;inset:0;z-index:40;background:rgba(228,228,225,.97);display:none;align-items:center;justify-content:center;padding:22px}
.overlay.show{display:flex}
.login-box{width:min(430px,100%);border:1px solid var(--ink);padding:28px;background:var(--paper)}
.login-box .big{font-size:40px;letter-spacing:-.08em;line-height:.9;font-weight:900;text-transform:uppercase;margin:24px 0 15px}
.login-box p{font-size:12px;color:var(--muted);margin:0 0 20px}
.login-box form{display:grid;gap:12px}
.error{color:#6b3833;font-size:11px;min-height:16px}
@media(max-width:900px){.shell{padding:0 20px}.hero{min-height:310px}.wave{width:78%;opacity:.65}.content-grid{grid-template-columns:1fr}.side-stack{grid-template-columns:repeat(2,minmax(0,1fr))}.action-layout{grid-template-columns:repeat(2,minmax(0,1fr));row-gap:20px}.action-card:nth-child(2){border-right:0;margin-right:0}.action-card:nth-child(3){border-right:1px solid var(--line)}.action-card:nth-child(4){border-right:0;margin-right:0}}
@media(max-width:600px){.shell{padding:0 16px}.topbar{padding:16px 0;align-items:flex-start}.nav{gap:12px;justify-content:flex-end}.nav a{font-size:9px}.nav a:nth-child(n+3){display:none}.nav .logout{padding:7px 9px}.hero{padding-top:36px;min-height:305px}.hero h1{font-size:clamp(43px,13vw,68px);margin-top:23px}.wave{right:-24%;top:26px;width:105%;opacity:.48}.hero-bottom{align-items:start;flex-direction:column;gap:15px}.hero-bottom p{max-width:290px}.section-heading{align-items:flex-start;flex-direction:column;padding-top:22px}.section-heading h2{font-size:19px}.month-control{width:100%;justify-content:space-between}.month-control input{width:145px}.stats{grid-template-columns:repeat(2,minmax(0,1fr))}.stat{margin:0;padding:15px 10px 16px 0;border-bottom:1px solid var(--line)}.stat:nth-child(2){margin:0;padding-left:12px;border-right:0}.stat:nth-child(3){padding-top:16px}.stat:nth-child(4){padding-left:12px;padding-top:16px;border-right:0}.stat .value{font-size:28px}.category-list{grid-template-columns:1fr}.category:nth-child(odd){padding-right:0;border-right:0}.category:nth-child(even){padding-left:0}.category{padding:15px 0}.side-stack{grid-template-columns:1fr}.action-layout{grid-template-columns:repeat(2,minmax(0,1fr));column-gap:14px}.action-card{padding:18px 0;border-right:0!important;margin:0!important}.action-card:nth-child(odd){padding-right:14px;border-right:1px solid var(--line)!important}.action-card h3{font-size:12px}.action-card p{min-height:0}.payment-list{grid-template-columns:1fr}.form-grid{grid-template-columns:1fr}.form-grid .wide{grid-column:auto}.footer{align-items:flex-start;flex-direction:column;gap:7px}}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*{transition:none!important}}

/* Final responsive fixes: forms use the available width on phones. */
.home-shortcuts{display:none!important}
.bottom-nav{grid-template-columns:repeat(5,minmax(0,1fr))}
.bottom-nav button[data-view-target="more"]{display:none!important}
.operation-forms{grid-template-columns:repeat(2,minmax(0,1fr));gap:28px;border-bottom:1px solid var(--line)}
.operation-forms .action-card{min-width:0;margin:0;padding:22px 20px 24px 0}
.operation-forms .action-card:first-child{border-right:1px solid var(--line);padding-right:26px}
.operation-forms .action-card:nth-child(2){border-right:0;margin:0;padding-right:0;padding-left:0}
.operation-forms .action-card .form-grid{grid-template-columns:minmax(0,1fr)}
.operation-forms .action-card .form-grid .wide{grid-column:auto}
@media(max-width:600px){
  .operation-forms{grid-template-columns:minmax(0,1fr);gap:0}
  .operation-forms .action-card{border-right:0!important;border-bottom:1px solid var(--line);padding:22px 0!important}
  .operation-forms .action-card .form-grid{grid-template-columns:minmax(0,1fr)}
}

</style>
</head>
<body>
<div class="shell" id="appShell">
<header class="topbar">
  <div class="brand">FAM / BUDGET<small>СЕМЕЙНАЯ ФИНАНСОВАЯ СИСТЕМА</small></div>
  <nav class="nav" aria-label="Управление аккаунтом">
    <button class="logout" id="logoutButton" type="button">Выйти ↗︎</button>
  </nav>
</header>
<main>
<section class="app-view active" data-view="home" id="view-home">
<section class="hero" id="overview">
  <div class="eyebrow">Личный финансовый кабинет / <span id="heroMonth">Текущий месяц</span></div>
  <svg class="wave" viewBox="0 0 680 300" fill="none" aria-hidden="true">
    <g stroke="#171715" stroke-width="1" opacity=".72">
      <path d="M0 155 C90 95 145 30 225 70 S340 230 415 150 S530 35 680 75"/>
      <path d="M0 161 C90 101 145 36 225 76 S340 236 415 156 S530 41 680 81"/>
      <path d="M0 167 C90 107 145 42 225 82 S340 242 415 162 S530 47 680 87"/>
      <path d="M0 173 C90 113 145 48 225 88 S340 248 415 168 S530 53 680 93"/>
      <path d="M0 179 C90 119 145 54 225 94 S340 254 415 174 S530 59 680 99"/>
      <path d="M0 185 C90 125 145 60 225 100 S340 260 415 180 S530 65 680 105"/>
      <path d="M0 191 C90 131 145 66 225 106 S340 266 415 186 S530 71 680 111"/>
      <path d="M0 197 C90 137 145 72 225 112 S340 272 415 192 S530 77 680 117"/>
      <path d="M0 203 C90 143 145 78 225 118 S340 278 415 198 S530 83 680 123"/>
      <path d="M0 209 C90 149 145 84 225 124 S340 284 415 204 S530 89 680 129"/>
      <path d="M0 215 C90 155 145 90 225 130 S340 290 415 210 S530 95 680 135"/>
      <path d="M0 221 C90 161 145 96 225 136 S340 296 415 216 S530 101 680 141"/>
      <path d="M0 227 C90 167 145 102 225 142 S340 302 415 222 S530 107 680 147"/>
      <path d="M0 233 C90 173 145 108 225 148 S340 308 415 228 S530 113 680 153"/>
      <path d="M0 239 C90 179 145 114 225 154 S340 314 415 234 S530 119 680 159"/>
      <path d="M0 245 C90 185 145 120 225 160 S340 320 415 240 S530 125 680 165"/>
      <path d="M0 251 C90 191 145 126 225 166 S340 326 415 246 S530 131 680 171"/>
      <path d="M0 257 C90 197 145 132 225 172 S340 332 415 252 S530 137 680 177"/>
      <path d="M0 263 C90 203 145 138 225 178 S340 338 415 258 S530 143 680 183"/>
      <path d="M0 269 C90 209 145 144 225 184 S340 344 415 264 S530 149 680 189"/>
      <path d="M0 275 C90 215 145 150 225 190 S340 350 415 270 S530 155 680 195"/>
      <path d="M0 281 C90 221 145 156 225 196 S340 356 415 276 S530 161 680 201"/>
      <path d="M0 287 C90 227 145 162 225 202 S340 362 415 282 S530 167 680 207"/>
    </g>
  </svg>
  <h1>Деньги<span>под контролем</span></h1>
  <div class="hero-bottom">
    <p>Один экран для реальных денег, категорий, обязательных платежей и накоплений. Данные сохраняются в общей базе семейного бюджета.</p>
    <button class="pill primary" type="button" data-view-target="operations">Управлять бюджетом ↘︎</button>
  </div>
</section>

<section class="stats" aria-label="Главные показатели">
  <div class="stat"><div class="label">Реальные деньги</div><div class="value" id="mainBalance">—</div><div class="note">Основной счёт после копилки</div></div>
  <div class="stat"><div class="label">Накоплено</div><div class="value" id="savingsBalance">—</div><div class="note" id="savingsNote">Копилка</div></div>
  <div class="stat"><div class="label">Потрачено за месяц</div><div class="value" id="spentTotal">—</div><div class="note" id="spentNote">Все категории</div></div>
  <div class="stat"><div class="label">Обязательные платежи</div><div class="value" id="paymentsCount">—</div><div class="note" id="paymentsNote">За выбранный месяц</div></div>
</section>

</section>

<section class="app-view" data-view="categories" id="view-categories">
<section class="section-heading">
  <div><h2>Бюджет по категориям</h2><p>Фактические траты и месячные лимиты</p></div>
  <div class="month-control"><label for="monthPicker" style="margin:0">Период</label><input type="month" id="monthPicker" aria-label="Выбрать месяц"></div>
</section>
<section class="category-only">
<div class="category-list" id="categoryList"><div class="empty">Загружаю категории…</div></div>
</section>
</section>

<section class="app-view" data-view="credits" id="view-credits">
<section class="section-heading">
  <div><h2>Кредиты</h2><p>Кредитная карта, автокредит, ипотека и обязательные платежи. Здесь можно внести фактическую оплату.</p></div>
</section>
<section class="section-heading" id="payments">
  <div><h2>Обязательные платежи</h2><p>Показываются только уже существующие платежи в базе — новые будущие события не создаются.</p></div>
</section>
<section class="payment-list" id="paymentList"><div class="empty">Загружаю платежи…</div></section>

</section>

<section class="app-view" data-view="savings" id="view-savings">
<section class="section-heading">
  <div><h2>Копилка</h2><p>Ты сама выбираешь сумму для накоплений. Автоматически ничего не откладывается.</p></div>
</section>
<section class="savings-layout">
<div class="line-card">
      <h3>🐷 Копилка</h3><p class="sub">Пополняйте на выбранную вами сумму. Автоматический выбор суммы для этого действия не используется.</p>
      <div class="metric-line"><span>Накоплено всего</span><strong id="savingsAmountLarge">—</strong></div>
      <div class="metric-line"><span>Цель месяца</span><strong id="savingsTarget">—</strong></div>
      <div class="metric-line"><span>До цели осталось</span><strong id="savingsRemaining">—</strong></div>
      <form id="savingsForm" class="form-grid" style="margin-top:14px">
        <div class="form-field wide"><label for="savingsInput">Сколько отложить, ₽</label><input id="savingsInput" type="number" min="0.01" step="0.01" placeholder="Например, 5000" required></div>
        <div class="form-field wide"><button class="button primary" type="submit">Пополнить копилку +</button></div>
      </form>
    </div>
</section>
</section>

<section class="app-view" data-view="operations" id="view-operations">
<section class="section-heading">
  <div><h2>Операции</h2><p>Добавляй доходы и расходы в общую базу семейного бюджета.</p></div>
</section>
<section class="action-layout operation-forms">
  <article class="action-card">
    <div class="action-number">01</div><h3>Добавить расход</h3><p>Категория, сумма и описание траты.</p>
    <form id="expenseForm" class="form-grid">
      <div class="form-field wide"><label for="expenseAmount">Сумма, ₽</label><input id="expenseAmount" type="number" step="0.01" min="0.01" placeholder="599" required></div>
      <div class="form-field wide"><label for="expenseCategory">Категория</label><select id="expenseCategory" required><option value="">Загрузка…</option></select></div>
      <div class="form-field wide"><label for="expenseDescription">Описание</label><input id="expenseDescription" maxlength="200" placeholder="Продукты, корм котам…"></div>
      <div class="form-field wide"><button class="button primary" type="submit">Записать расход</button></div>
    </form>
  </article>
  <article class="action-card">
    <div class="action-number">02</div><h3>Добавить доход</h3><p>Зарплата, аванс, кэшбэк или другой доход.</p>
    <form id="incomeForm" class="form-grid">
      <div class="form-field wide"><label for="incomeAmount">Сумма, ₽</label><input id="incomeAmount" type="number" min="0.01" step="0.01" placeholder="50000" required></div>
      <div class="form-field wide"><label for="incomeDescription">Источник дохода</label><input id="incomeDescription" maxlength="100" placeholder="Зарплата, кэшбэк…" required></div>
      <div class="form-field wide"><button class="button" type="submit">Записать доход</button></div>
    </form>
  </article>
</section>

<section class="app-view" data-view="more" id="view-more">
<section class="section-heading">
  <div><h2>Ещё</h2><p>Реальный остаток, история операций и корректировки баланса.</p></div>
</section>
<section class="balance-layout">
<div class="line-card">
      <h3>Реальные деньги</h3><p class="sub">Укажите сумму, которая действительно есть на основном счёте. История расходов и доходов останется без изменений.</p>
      <form id="balanceForm" class="form-grid">
        <div class="form-field wide"><label for="balanceInput">Фактический остаток, ₽</label><input id="balanceInput" type="number" min="0" step="0.01" placeholder="Введите сумму" required></div>
        <div class="form-field wide"><button class="button" type="submit">Сохранить реальный остаток</button></div>
      </form>
      <div class="metric-line" style="margin-top:10px"><span>Последняя корректировка</span><strong id="lastAdjustment">—</strong></div>
    </div>
</section>
<section class="section-heading" id="history">
  <div><h2>История операций</h2><p>Доходы, расходы и назначения зафиксированных корректировок</p></div>
</section>
<div class="table-wrap">
<table>
<thead><tr><th>Дата</th><th>Операция</th><th>Описание</th><th>Категория / долг</th><th class="right">Сумма</th></tr></thead>
<tbody id="operationTable"><tr><td colspan="5" class="empty">Загружаю историю…</td></tr></tbody>
</table>
</div>
<section class="section-heading">
  <div><h2>Корректировки остатка</h2><p>Отдельная история правок реальных денег. Не влияет на статистику доходов и расходов.</p></div>
</section>
<div class="table-wrap">
<table>
<thead><tr><th>Когда</th><th>Причина</th><th>Было</th><th>Стало</th><th class="right">Разница</th></tr></thead>
<tbody id="adjustmentTable"><tr><td colspan="5" class="empty">Нет корректировок</td></tr></tbody>
</table>
</div>

</section>
</main>
<nav class="bottom-nav" id="bottomNav" aria-label="Разделы приложения">
  <button class="active" type="button" data-view-target="home" aria-current="page"><span class="tab-icon">⌂</span><span class="tab-label">Главная</span></button>
  <button type="button" data-view-target="categories"><span class="tab-icon">▦</span><span class="tab-label">Категории</span></button>
  <button type="button" data-view-target="credits"><span class="tab-icon">₽</span><span class="tab-label">Кредиты</span></button>
  <button type="button" data-view-target="savings"><span class="tab-icon">◉</span><span class="tab-label">Копилка</span></button>
  <button type="button" data-view-target="operations"><span class="tab-icon">＋</span><span class="tab-label">Операции</span></button>
</nav>
<div class="footer-wave" aria-hidden="true">
<svg viewBox="0 0 1200 170" preserveAspectRatio="none" fill="none">
<defs><linearGradient id="waveTint" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#111"/><stop offset=".53" stop-color="#8caaa3"/><stop offset="1" stop-color="#a9a1bc"/></linearGradient></defs>
<g stroke="url(#waveTint)" stroke-width="1" opacity=".8">
<path d="M0 48 C130 40 170 130 310 90 S510 10 650 75 S850 145 980 82 S1110 45 1200 60"/>
<path d="M0 54 C130 46 170 136 310 96 S510 16 650 81 S850 151 980 88 S1110 51 1200 66"/>
<path d="M0 60 C130 52 170 142 310 102 S510 22 650 87 S850 157 980 94 S1110 57 1200 72"/>
<path d="M0 66 C130 58 170 148 310 108 S510 28 650 93 S850 163 980 100 S1110 63 1200 78"/>
<path d="M0 72 C130 64 170 154 310 114 S510 34 650 99 S850 169 980 106 S1110 69 1200 84"/>
<path d="M0 78 C130 70 170 160 310 120 S510 40 650 105 S850 175 980 112 S1110 75 1200 90"/>
<path d="M0 84 C130 76 170 166 310 126 S510 46 650 111 S850 181 980 118 S1110 81 1200 96"/>
<path d="M0 90 C130 82 170 172 310 132 S510 52 650 117 S850 187 980 124 S1110 87 1200 102"/>
<path d="M0 96 C130 88 170 178 310 138 S510 58 650 123 S850 193 980 130 S1110 93 1200 108"/>
<path d="M0 102 C130 94 170 184 310 144 S510 64 650 129 S850 199 980 136 S1110 99 1200 114"/>
<path d="M0 108 C130 100 170 190 310 150 S510 70 650 135 S850 205 980 142 S1110 105 1200 120"/>
<path d="M0 114 C130 106 170 196 310 156 S510 76 650 141 S850 211 980 148 S1110 111 1200 126"/>
</g></svg>
</div>
<footer class="footer shell"><span>FAM / BUDGET — СЕМЕЙНЫЙ БЮДЖЕТ</span><span>Данные сохранены в общей базе Cloudflare D1</span></footer>
</div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<div class="overlay" id="loginOverlay">
  <div class="login-box">
    <div class="eyebrow">FAM / BUDGET — ДОСТУП ДЛЯ СЕМЬИ</div>
    <div class="big">Деньги<br>под контролем</div>
    <p id="loginMessage">Введи пароль веб-приложения, чтобы открыть семейный бюджет.</p>
    <form id="loginForm">
      <div><label for="passwordInput">Пароль</label><input id="passwordInput" type="password" autocomplete="current-password" required></div>
      <button class="button primary" type="submit">Войти в бюджет →</button>
      <div class="error" id="loginError"></div>
    </form>
  </div>
</div>
<script>
(function(){
'use strict';
var state = {data:null, month:'', busy:false};
var $ = function(id){return document.getElementById(id);};
var numberFormat = new Intl.NumberFormat('ru-RU',{minimumFractionDigits:0,maximumFractionDigits:2});
function money(value){return numberFormat.format(Number(value||0))+' ₽';}
function escapeHtml(value){return String(value==null?'':value).replace(/[&<>"']/g,function(ch){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];});}
function showToast(message){var toast=$('toast');toast.textContent=message;toast.classList.add('show');window.setTimeout(function(){toast.classList.remove('show');},4200);}
function setBusy(value){state.busy=value;$('appShell').classList.toggle('loading',value);}
async function api(path, options){
  var config=options||{};
  config.credentials='same-origin';
  config.headers=Object.assign({'Content-Type':'application/json'},config.headers||{});
  var response;
  try{response=await fetch(path,config);}catch(e){throw new Error('Не удалось подключиться к приложению. Проверь интернет.');}
  var payload={};
  try{payload=await response.json();}catch(e){}
  if(response.status===401&&payload.unauthorized){$('loginOverlay').classList.add('show');throw new Error('Нужно войти заново.');}
  if(!response.ok){
    if(response.status===503&&payload.password_configured===false){$('loginOverlay').classList.add('show');$('loginMessage').textContent=payload.error||'Пароль веб-приложения не настроен.';$('loginForm').style.display='none';}
    throw new Error(payload.error||'Запрос не выполнен.');
  }
  return payload;
}
function currentMonth(){return new Date().toISOString().slice(0,7);}
function showLogin(){ $('loginOverlay').classList.add('show'); $('loginError').textContent=''; }

function showView(viewName){
  var allowed=['home','categories','credits','savings','operations','more'];
  if(allowed.indexOf(viewName)<0)viewName='home';
  Array.prototype.forEach.call(document.querySelectorAll('.app-view'),function(view){
    var active=view.getAttribute('data-view')===viewName;
    view.classList.toggle('active',active);
    view.setAttribute('aria-hidden',active?'false':'true');
  });
  Array.prototype.forEach.call($('bottomNav').querySelectorAll('[data-view-target]'),function(button){
    var active=button.getAttribute('data-view-target')===viewName;
    button.classList.toggle('active',active);
    if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
  });
  window.scrollTo({top:0,behavior:'auto'});
}
function fillCategories(categories){
  $('expenseCategory').innerHTML='<option value="">Выбрать категорию</option>'+categories.map(function(c){return '<option value="'+escapeHtml(c.name)+'">'+escapeHtml(c.name)+'</option>';}).join('');
}
function render(data){
  state.data=data;state.month=data.month;
  var r=data.report,b=data.budget;
  $('monthPicker').value=data.month;
  $('heroMonth').textContent=data.month;
  $('mainBalance').textContent=money(r.main_account);
  $('savingsBalance').textContent=money(r.savings_balance);
  $('savingsNote').textContent='Отложено за месяц: '+money(r.monthly_savings);
  $('spentTotal').textContent=money(r.life_expenses);
  $('spentNote').textContent='Лимит бюджета: '+money(r.life_budget);
  var pending=data.payments.filter(function(p){return p.status!=='paid';}).length;
  $('paymentsCount').textContent=String(pending);
  $('paymentsNote').textContent='Не оплачено · всего '+data.payments.length;
  $('savingsAmountLarge').textContent=money(r.savings_balance);
  $('savingsTarget').textContent=money(r.savings_target);
  $('savingsRemaining').textContent=money(r.savings_remaining);
  $('balanceInput').value=Number(r.main_account||0).toFixed(2);
  $('lastAdjustment').textContent=data.adjustments.length?money(data.adjustments[0].target_balance):'Не менялся';
  fillCategories(r.categories||[]);
  renderCategories(r.categories||[]);
  renderPayments(data.payments||[]);
  renderOperations(data.operations||[]);
  renderAdjustments(data.adjustments||[]);
}
function renderCategories(categories){
  if(!categories.length){$('categoryList').innerHTML='<div class="empty">Категории не найдены.</div>';return;}
  $('categoryList').innerHTML=categories.map(function(c){
    var limit=Number(c.limit||0),spent=Number(c.spent||0),allocated=Number(c.allocated||0);
    var progress=limit>0?Math.min(100,spent/limit*100):0;
    return '<article class="category"><div class="category-top"><div class="category-name">'+escapeHtml(c.name)+'</div><div class="category-amount">'+money(spent)+' / '+money(limit)+'</div></div><div class="category-meta"><span>Распределено: '+money(allocated)+'</span><span>Осталось по лимиту: '+money(Math.max(limit-spent,0))+'</span></div><div class="track"><span style="width:'+progress.toFixed(2)+'%"></span></div></article>';
  }).join('');
}
function renderPayments(payments){
  if(!payments.length){$('paymentList').innerHTML='<div class="empty">В базе нет обязательных платежей за выбранный месяц. Будущие события автоматически не создавались.</div>';return;}
  $('paymentList').innerHTML=payments.map(function(p){
    var dateText=p.event_date||'';
    if(p.planned_day){var bits=String(dateText).split('-');dateText=(bits.length===3?bits[2]+'.'+bits[1]:dateText);}
    var paid=p.status==='paid';
    return '<article class="payment-item"><div><h4>'+escapeHtml(p.payment_name)+'</h4><p>'+escapeHtml(dateText)+' · План '+money(p.planned_amount)+(paid?' · Факт '+money(p.actual_amount):'')+'</p></div><div style="text-align:right;display:grid;justify-items:end;gap:7px"><span class="status '+(paid?'paid':'')+'">'+(paid?'Оплачено':'Ожидает оплаты')+'</span>'+(paid?'':'<button class="button" type="button" data-payment="'+Number(p.id)+'" data-payment-name="'+escapeHtml(p.payment_name)+'">Записать оплату</button>')+'</div></article>';
  }).join('');
  Array.prototype.forEach.call($('paymentList').querySelectorAll('[data-payment]'),function(button){
    button.addEventListener('click',async function(){
      var raw=window.prompt('Фактическая сумма платежа «'+button.getAttribute('data-payment-name')+'», ₽');
      if(raw===null)return;
      var amount=Number(String(raw).replace(/\s/g,'').replace(',','.'));
      if(!Number.isFinite(amount)||amount<=0){showToast('Введи корректную сумму больше нуля.');return;}
      try{setBusy(true);await api('/api/payment',{method:'POST',body:JSON.stringify({payment_id:Number(button.getAttribute('data-payment')),amount:amount})});await reload();showToast('Платёж записан.');}
      catch(error){showToast(error.message);}
      finally{setBusy(false);}
    });
  });
}
function renderOperations(operations){
  if(!operations.length){$('operationTable').innerHTML='<tr><td colspan="5" class="empty">Операций пока нет.</td></tr>';return;}
  $('operationTable').innerHTML=operations.map(function(o){
    var isIncome=o.operation_type==='income';
    var type=isIncome?'Доход':'Расход';
    var name=o.description||o.debt_name||type;
    var group=o.category_name||o.debt_name||'—';
    var isPetFood=!isIncome&&o.category_name==='Питомцы'&&/корм|грандорф|grandorf|jarvi|джарви/i.test(name);
    var stockButton=isPetFood?'<button class="button" type="button" data-stock-id="'+Number(o.id)+'" data-stock-months="'+Number(o.stock_months||0)+'">'+(o.stock_months?'Запас: '+Number(o.stock_months)+' мес.':'Отметить запас')+'</button>':'';
    return '<tr><td>'+escapeHtml(o.operation_date)+'</td><td><span class="type">'+type+'</span></td><td>'+escapeHtml(name)+(stockButton?'<div style="margin-top:8px">'+stockButton+'</div>':'')+'</td><td>'+escapeHtml(group)+'</td><td class="right '+(isIncome?'positive':'negative')+'">'+(isIncome?'+':'−')+money(o.amount)+'</td></tr>';
  }).join('');
  Array.prototype.forEach.call($('operationTable').querySelectorAll('[data-stock-id]'),function(button){
    button.addEventListener('click',async function(){
      var raw=window.prompt('На сколько месяцев хватит этого корма? Введи число от 1 до 24.',button.getAttribute('data-stock-months')||'3');
      if(raw===null)return;
      var months=Number(raw);
      if(!Number.isInteger(months)||months<1||months>24){showToast('Укажи срок от 1 до 24 месяцев.');return;}
      try{setBusy(true);await api('/api/stock',{method:'POST',body:JSON.stringify({operation_id:Number(button.getAttribute('data-stock-id')),months:months})});await reload();showToast('Срок запаса записан.');}
      catch(error){showToast(error.message);}
      finally{setBusy(false);}
    });
  });
}
function renderAdjustments(items){
  if(!items.length){$('adjustmentTable').innerHTML='<tr><td colspan="5" class="empty">Реальный остаток ещё не корректировали.</td></tr>';return;}
  $('adjustmentTable').innerHTML=items.map(function(a){
    return '<tr><td>'+escapeHtml(a.created_at)+'</td><td>'+escapeHtml(a.note||'Корректировка')+'</td><td>'+money(a.previous_balance)+'</td><td>'+money(a.target_balance)+'</td><td class="right '+(Number(a.delta)>=0?'positive':'negative')+'">'+(Number(a.delta)>=0?'+':'−')+money(Math.abs(Number(a.delta)))+'</td></tr>';
  }).join('');
}
async function reload(month){
  var selected=month||$('monthPicker').value;
  var path='/api/dashboard';
  if(selected)path+='?month='+encodeURIComponent(selected);
  var data=await api(path,{method:'GET',headers:{}});
  render(data);
}
async function submitForm(form, path, buildBody, successMessage, onSuccess){
  if(state.busy)return;
  try{
    setBusy(true);
    var body=buildBody();
    var result=await api(path,{method:'POST',body:JSON.stringify(body)});
    form.reset();
    if(onSuccess)onSuccess(result);
    var warning=result&&(result.allocation_warning||(result.result&&result.result.allocation_warning));
    showToast(warning?successMessage+' '+warning:successMessage);
    try{await reload();}catch(refreshError){showToast(successMessage+' Обнови страницу, чтобы проверить новый остаток.');}
  }
  catch(error){showToast(error.message);}
  finally{setBusy(false);}
}
$('loginForm').addEventListener('submit',async function(event){
  event.preventDefault();$('loginError').textContent='';
  try{
    var response=await fetch('/api/login',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:$('passwordInput').value})});
    var data={};try{data=await response.json();}catch(e){}
    if(!response.ok){$('loginError').textContent=data.error||'Не удалось войти.';return;}
    $('loginOverlay').classList.remove('show');$('passwordInput').value='';$('loginForm').style.display='grid';$('loginMessage').textContent='Введи пароль веб-приложения, чтобы открыть семейный бюджет.';
    showView('home');await reload();showToast('Вход выполнен.');
  }catch(e){$('loginError').textContent='Не удалось подключиться. Попробуй ещё раз.';}
});
$('logoutButton').addEventListener('click',async function(){try{await api('/api/logout',{method:'POST',body:'{}'});}catch(e){}showLogin();});

Array.prototype.forEach.call(document.querySelectorAll('[data-view-target]'),function(button){
  button.addEventListener('click',function(event){
    event.preventDefault();
    showView(button.getAttribute('data-view-target'));
  });
});
$('monthPicker').addEventListener('change',async function(){try{setBusy(true);await reload($('monthPicker').value);}catch(error){showToast(error.message);}finally{setBusy(false);}});
$('expenseForm').addEventListener('submit',function(event){event.preventDefault();submitForm(event.currentTarget,'/api/expense',function(){return {amount:$('expenseAmount').value,category:$('expenseCategory').value,description:$('expenseDescription').value};},'Расход записан.');});
$('incomeForm').addEventListener('submit',function(event){event.preventDefault();submitForm(event.currentTarget,'/api/income',function(){return {amount:$('incomeAmount').value,description:$('incomeDescription').value};},'Доход записан.');});
var pendingSavingsRequestId='';
$('savingsForm').addEventListener('submit',function(event){
  event.preventDefault();
  if(!pendingSavingsRequestId)pendingSavingsRequestId=window.crypto&&window.crypto.randomUUID?window.crypto.randomUUID():('req_'+Date.now()+'_'+Math.random().toString(36).slice(2));
  submitForm(event.currentTarget,'/api/savings',function(){return {amount:$('savingsInput').value,request_id:pendingSavingsRequestId};},'Пополнение копилки подтверждено.',function(){pendingSavingsRequestId='';});
});
$('balanceForm').addEventListener('submit',function(event){event.preventDefault();var target=Number($('balanceInput').value);if(!Number.isFinite(target)||target<0){showToast('Введи реальный остаток не меньше нуля.');return;}if(!window.confirm('Установить реальный остаток '+money(target)+'? История доходов и расходов не изменится.'))return;submitForm(event.currentTarget,'/api/balance',function(){return {amount:target};},'Реальный остаток обновлён.');});
(async function init(){
  try{await reload();}catch(error){if(error.message!=='Нужно войти заново.')showToast(error.message);}
})();
})();
</script>
</body>
</html>
'''