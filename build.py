#!/usr/bin/env python3
"""Build the static site from src/ into public/.

    python3 build.py

Pages live in src/pages/ and start with a JSON meta block:

    <!--meta {"title": "...", "description": "...", "path": "/about/"} -->
    <!--head--> ...extra <head> markup, e.g. JSON-LD... <!--/head-->
    ...page body (everything between the header and footer)...

Anywhere in pages or partials:
    {{ key }}               value from src/site.json or the page's meta
    {% include name.html %} contents of src/partials/name.html

Site-wide details (brand name, domain, phone, RERA, form key, GA id) live in
src/site.json, so renaming the site is a one-file change followed by a rebuild.
"""
import datetime
import html
import json
import re
import shutil
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).parent
SRC = ROOT / "src"
OUT = ROOT / "public"

META_RE = re.compile(r"\A\s*<!--meta\s*(\{.*?\})\s*-->", re.S)
HEAD_RE = re.compile(r"<!--head-->(.*?)<!--/head-->", re.S)
INCLUDE_RE = re.compile(r"{%\s*include\s+([\w.-]+)\s*%}")
VAR_RE = re.compile(r"{{\s*([\w.]+)\s*}}")


def analytics(ga_id):
    if not ga_id:
        return ""
    return f"""<script async src="https://www.googletagmanager.com/gtag/js?id={ga_id}"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){{dataLayer.push(arguments);}}
      gtag('js', new Date());
      gtag('config', '{ga_id}');
    </script>"""


def zendesk(key):
    if not key:
        return ""
    # Lift the launcher above the fixed bottom CTA bar (classic widget reads
    # zESettings; the messaging widget is nudged by CSS in site.css).
    return f"""<script>
      window.zESettings = {{ webWidget: {{ position: {{ horizontal: "right", vertical: "bottom" }}, offset: {{ vertical: "70px", mobile: {{ vertical: "70px" }} }} }} }};
    </script>
    <script id="ze-snippet" src="https://static.zdassets.com/ekr/snippet.js?key={key}" defer></script>"""


def render(text, ctx, source):
    def var(m):
        key = m.group(1)
        if key not in ctx:
            raise KeyError(f"{source}: unknown template variable '{key}'")
        return str(ctx[key])

    # Repeat until stable: the page body, partials and meta values can all
    # contain further includes and variables.
    for _ in range(6):
        expanded = INCLUDE_RE.sub(lambda m: (SRC / "partials" / m.group(1)).read_text(), text)
        expanded = VAR_RE.sub(var, expanded)
        if expanded == text:
            return text
        text = expanded
    raise RecursionError(f"{source}: includes/variables nested too deeply")


FAQ_RE = re.compile(r"<details>\s*<summary>(.*?)</summary>\s*<div>(.*?)</div>\s*</details>", re.S)


def plain(fragment):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment))).strip()


def faq_schema(page_html):
    """FAQPage JSON-LD built from the page's visible <details> FAQ, so the two never drift."""
    items = [
        {"@type": "Question", "name": plain(q), "acceptedAnswer": {"@type": "Answer", "text": plain(a)}}
        for q, a in FAQ_RE.findall(page_html)
    ]
    if not items:
        return ""
    data = json.dumps({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": items},
                      ensure_ascii=False, indent=2)
    return f'<script type="application/ld+json">\n{data}\n</script>\n  '


def project_card(p):
    e = html.escape
    return f"""<article class="project-card">
        <a class="project-card-media" href="/projects/{p['slug']}/">
          <img src="/images/{p['slug']}/{p['slug']}-card.webp" alt="{e(p['name'])}, {e(p['locality'])}" width="800" height="500" loading="lazy" />
          <span class="project-card-tag">{e(p['status'])}</span>
        </a>
        <div class="project-card-body">
          <h3><a href="/projects/{p['slug']}/">{e(p['name'])}</a></h3>
          <p class="loc">📍 {e(p['locality'])}</p>
          <div class="chips"><span class="chip">{e(p['type'])}</span><span class="chip">{e(p['config'])}</span><span class="chip">{e(p['price'])}</span></div>
          <div class="actions"><a class="btn btn-outline-dark" href="/projects/{p['slug']}/">View project</a></div>
        </div>
      </article>"""


def related_projects(slug, projects, n=3):
    """Same corridor first, then same property type, then the rest."""
    me = next(p for p in projects if p["slug"] == slug)
    others = [p for p in projects if p["slug"] != slug]
    others.sort(key=lambda p: (p["corridor"] != me["corridor"], p["type"] != me["type"]))
    return others[:n]


def project_groups(projects, corridors):
    sections = []
    for c in corridors:
        cards = "\n      ".join(project_card(p) for p in projects if p["corridor"] == c["id"])
        sections.append(f"""<section class="section{' alt' if len(sections) % 2 else ''}" id="{c['id']}">
  <div class="container">
    <div class="section-title left">
      <p class="eyebrow">{html.escape(c['eyebrow'])}</p>
      <h2>{html.escape(c['name'])}</h2>
      <p>{html.escape(c['intro'])}</p>
    </div>
    <div class="grid three">
      {cards}
    </div>
  </div>
</section>""")
    return "\n".join(sections)


def project_schema(p, meta):
    """Breadcrumb + Residence JSON-LD for a project page. {{ }} placeholders are filled at render."""
    url = "{{ base_url }}/projects/" + p["slug"] + "/"
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": "{{ base_url }}/"},
                {"@type": "ListItem", "position": 2, "name": "Projects", "item": "{{ base_url }}/projects/"},
                {"@type": "ListItem", "position": 3, "name": p["name"], "item": url},
            ]},
            {"@type": "Residence", "name": p["name"], "url": url,
             "description": meta["description"],
             "image": "{{ base_url }}/images/" + p["slug"] + "/" + p["slug"] + "-share.jpg",
             "address": {"@type": "PostalAddress", "addressLocality": p["locality"],
                         "addressRegion": "Karnataka", "addressCountry": "IN"}},
        ],
    }
    return '<script type="application/ld+json">\n' + json.dumps(data, ensure_ascii=False, indent=2) + "\n</script>"


EMI_RATE, EMI_YEARS = 0.085, 20


def inr(amount):
    """Format rupees the Indian way: ₹1.52 Cr, ₹71 L, ₹63,214."""
    if amount >= 1e7:
        return f"₹{amount / 1e7:.2f} Cr"
    if amount >= 1e5:
        return f"₹{amount / 1e5:.1f} L".replace(".0 L", " L")
    return "₹{:,}".format(round(amount))


def inr_exact(amount):
    """₹1,05,530 — Indian digit grouping, for EMIs."""
    s = str(round(amount))
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return "₹" + ",".join(groups + [tail]) if groups else "₹" + tail


def emi_section(p, meta):
    """Illustrative loan table from the page's "emi": [[label, price], ...] meta."""
    rows = meta.get("emi")
    if not rows:
        return ""
    ltv = meta.get("emi_ltv", 0.8)
    r, n = EMI_RATE / 12, EMI_YEARS * 12
    body = []
    for label, price in rows:
        loan = price * ltv
        emi = loan * r * (1 + r) ** n / ((1 + r) ** n - 1)
        body.append(f"<tr><th scope=\"row\">{html.escape(label)}</th><td>{inr(price)}</td><td>{inr(loan)}</td>"
                    f"<td class=\"price-cell\">{inr_exact(emi)} / month</td><td>{inr(price - loan)}</td></tr>")
    kind = meta.get("emi_kind") or ("plot loan" if ltv < 0.8 else "home loan")
    return f"""<section class="section alt" id="emi">
  <div class="container">
    <div class="section-title">
      <p class="eyebrow">Financing</p>
      <h2>{html.escape(p['name'])}: Illustrative {kind.title()} EMIs</h2>
      <p>Assuming a {round(ltv * 100)}% {kind} over {EMI_YEARS} years at about {EMI_RATE * 100:g}% interest. Your lender's rate, tenure and eligibility will differ; this is to help you size the commitment.</p>
    </div>
    <div class="table-wrap">
      <table class="spec-table">
        <thead><tr><th scope="col">Home</th><th scope="col">Base price</th><th scope="col">Loan</th><th scope="col">Approx. EMI</th><th scope="col">Your share</th></tr></thead>
        <tbody>
          {''.join(body)}
        </tbody>
      </table>
    </div>
    <p class="muted mt-lg">"Your share" is the down payment on the base price only. Stamp duty, registration and most developer charges are usually paid from your own funds on top. During construction, banks typically disburse in stages and you pay interest only (pre-EMI) on what's been released.</p>
  </div>
</section>"""


def project_contexts(meta, data):
    projects, corridors = data["projects"], data["corridors"]
    ctx = {
        "project_schema": "",
        "emi_section": "",
        "project_count": len(projects),
        "project_groups": project_groups(projects, corridors),
        "project_options": "".join(
            f'<option value="{html.escape(p["name"])}">{html.escape(p["name"])}, {html.escape(p["locality"])}</option>'
            for p in sorted(projects, key=lambda p: p["name"])),
        "corridor_links": " · ".join(
            f'<a href="/projects/#{c["id"]}">{html.escape(c["short"])}</a>' for c in corridors),
    }
    if "featured" in meta:
        by_slug = {p["slug"]: p for p in projects}
        ctx["featured_projects"] = "\n      ".join(project_card(by_slug[s]) for s in meta["featured"])
    if "project" in meta:
        p = next(p for p in projects if p["slug"] == meta["project"])
        ctx["project_name"] = p["name"]
        ctx["project_locality"] = p["locality"]
        ctx["related_projects"] = "\n      ".join(project_card(r) for r in related_projects(p["slug"], projects))
        ctx["config_options"] = "".join(
            f'<option value="{html.escape(c)}">{html.escape(c)}</option>' for c in meta.get("configs", []))
        ctx["og_image"] = f"/images/{p['slug']}/{p['slug']}-share.jpg"
        ctx["project_schema"] = project_schema(p, meta)
        ctx["emi_section"] = emi_section(p, meta)
        ctx["project_wa"] = urllib.parse.quote(
            f"Hi, I'd like details on {p['name']}: open units, the price sheet and a site visit.")
    return ctx


SITE_NAV = [("Home", "/"), ("Projects", "/projects/"), ("About", "/about/"),
            ("Reviews", "/testimonials/"), ("Contact", "/contact/")]


SITE_NAV_HTML = "\n          ".join(f'<a href="{href}" data-nav="{href}">{label}</a>' for label, href in SITE_NAV)

# Project pages swap the site links for these groups. Every <section id> on a
# project page must belong to one group (or SECTION_UNGROUPED), so new sections
# can't silently fall outside the header. Links run in page order: each jumps
# to its group's first section on the page and is placed by where that falls.
# Groups with no sections on a page are left out.
SECTION_GROUPS = [
    ("Overview", "snapshot why design phases township in-depth gallery master-plan masterplan "
                 "masterplan-detail towers"),
    ("Floor Plans & Price",
     "homes plots plans sizes formats specs specs-ask rooms carpet duplex living layout "
     "block-plans layout-notes choose choose-home choose-unit choosing choosing-unit "
     "unit-guide special-units plot-maths build build-guide plot-vs-flat compare-plots "
     "phase-choice quality "
     "prices price-list pricing-detail per-sqft costs other-charges charges payment schedule "
     "eoi eoi-guide included emi price-context ownership-cost maintenance resale-pricing"),
    ("Amenities", "amenities amenities-full amenities-in-full amenities-detail clubhouse-detail parks "
                  "daily-life township-life residents association weekend"),
    ("Location", "location neighbourhood connectivity commute commutes travel distances area area-guide "
                 "address-compare compare-south compare market"),
    ("Guide", "weigh buyers fit checklist investment rental rentals resale-process investor by-buyer "
              "buyer-story first-time timeline dates outlook our-take how-we-help developer"),
    ("FAQs", "faq more-faq faq-3 faq-4 faq-5 phase-2-questions"),
]
SECTION_UNGROUPED = {"nearby", "enquire", "rera"}
SECTION_ID_RE = re.compile(r'<section\b[^>]*\bid="([^"]+)"')


def section_nav(page_html, project, source):
    """Header links for a project page, one per group, in page order."""
    group_of = {sid: label for label, ids in SECTION_GROUPS for sid in ids.split()}
    main = page_html[page_html.index("<main"):page_html.index("</main>")]
    members = {}
    for sid in SECTION_ID_RE.findall(main):
        if sid in SECTION_UNGROUPED:
            continue
        if sid not in group_of:
            raise KeyError(f"{source}: section '{sid}' isn't in any SECTION_GROUPS header group")
        members.setdefault(group_of[sid], []).append(sid)
    links = []
    for label, sids in members.items():
        if project["type"] == "Plots":
            label = label.replace("Floor Plans", "Plots")
        links.append(f'<a href="#{sids[0]}" data-sections="{" ".join(sids)}">{html.escape(label)}</a>')
    links.append('<a href="/projects/" class="nav-back">All Projects</a>')
    return "\n          ".join(links)


def mark_current_nav(page_html, path):
    return page_html.replace(f'data-nav="{path}"', f'data-nav="{path}" aria-current="page"')


def out_file(path):
    if path.endswith(".html"):
        return OUT / path.lstrip("/")
    return OUT / path.lstrip("/") / "index.html"


def main():
    site = json.loads((SRC / "site.json").read_text())
    layout = (SRC / "layout.html").read_text()
    data = json.loads((SRC / "projects.json").read_text())
    today = datetime.date.today().isoformat()

    # Empty public/ in place rather than deleting it, so a local server running
    # from inside the folder keeps working across rebuilds.
    OUT.mkdir(exist_ok=True)
    for child in OUT.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    shutil.copytree(SRC / "static", OUT, dirs_exist_ok=True)

    sitemap = []
    for page in sorted((SRC / "pages").rglob("*.html")):
        raw = page.read_text()
        m = META_RE.match(raw)
        if not m:
            raise ValueError(f"{page}: missing <!--meta {{...}} --> block")
        meta = json.loads(m.group(1))
        body = raw[m.end():]
        head = HEAD_RE.search(body)
        head_extra = head.group(1).strip() if head else ""
        body = HEAD_RE.sub("", body).strip()

        ctx = {
            **site,
            "year": datetime.date.today().year,
            "analytics": analytics(site.get("ga_id")),
            "zendesk": zendesk(site.get("zendesk_key")),
            "robots": "index, follow",
            "og_image": "/images/sattva-kaveri-siri/sattva-kaveri-siri-share.jpg",
            **project_contexts(meta, data),
            **meta,
        }
        ctx["canonical"] = site["base_url"].rstrip("/") + meta["path"]
        ctx["title_attr"] = html.escape(render(meta["title"], ctx, page), quote=True)
        ctx["description_attr"] = html.escape(render(meta["description"], ctx, page), quote=True)
        ctx["head_extra"] = head_extra
        ctx["content"] = body
        ctx["nav_links"] = "<!--section-nav-->" if "project" in meta else SITE_NAV_HTML
        # On project pages the logo scrolls back to the top instead of leaving the page.
        if "project" in meta:
            ctx["brand_href"], ctx["brand_label"] = "#top", "Back to top of page"
        else:
            ctx["brand_href"], ctx["brand_label"] = "/", f"{site['site_name']} home"

        rendered = mark_current_nav(render(layout, ctx, page), meta["path"])
        if "project" in meta:
            project = next(p for p in data["projects"] if p["slug"] == meta["project"])
            rendered = rendered.replace("<!--section-nav-->", section_nav(rendered, project, page), 1)
        if meta.get("faq_schema"):
            rendered = rendered.replace("</head>", faq_schema(rendered) + "</head>", 1)
        dest = out_file(meta["path"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered)
        print(f"  {meta['path']:<36} <- {page.relative_to(SRC)}")

        if "noindex" not in ctx["robots"]:
            sitemap.append((ctx["canonical"], meta.get("priority", "0.6")))

    urls = "\n".join(
        f"  <url><loc>{loc}</loc><lastmod>{today}</lastmod><priority>{prio}</priority></url>"
        for loc, prio in sitemap
    )
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n"
    )
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {site['base_url'].rstrip('/')}/sitemap.xml\n"
    )
    (OUT / "site.webmanifest").write_text(json.dumps({
        "name": site["site_name"],
        "short_name": site["site_name"],
        "icons": [
            {"src": "/images/brand/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/images/brand/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
        "theme_color": site["theme_color"],
        "background_color": "#f8f5f0",
        "display": "standalone",
    }, indent=2))
    print(f"Built {len(list(OUT.rglob('*.html')))} pages into {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
