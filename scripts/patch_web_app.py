from pathlib import Path


WEB_APP = Path("app/web_app.py")

CSS = """
/* UI cleanup: keep the dashboard focused and remove the unused More tab. */
.home-shortcuts{display:none!important}
.bottom-nav{grid-template-columns:repeat(5,minmax(0,1fr))}
.bottom-nav button:last-child{display:none!important}
.operation-forms{gap:0!important}
.operation-forms .action-card{margin:0!important}
.operation-forms .action-card:first-child{padding-right:32px!important}
.operation-forms .action-card:nth-child(2){padding-left:32px!important}
@media(max-width:600px){.operation-forms .action-card:first-child{padding-right:18px!important}.operation-forms .action-card:nth-child(2){padding-left:18px!important}}
"""


def main():
    text = WEB_APP.read_text(encoding="utf-8")
    marker = "</style>"
    if CSS.strip() not in text:
        if marker not in text:
            raise SystemExit("Could not find the web app style block")
        text = text.replace(marker, CSS + marker, 1)
        WEB_APP.write_text(text, encoding="utf-8")
        print("Applied Family Budget UI cleanup")
    else:
        print("Family Budget UI cleanup already applied")


if __name__ == "__main__":
    main()
