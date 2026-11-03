"""Generate the Frappe 16 desk files (desktop tile, Dock, Sidebars) for armak.

Edit SPEC, run from the repo root (apps/armak/), then `bench --site <site> migrate`.
Frappe 15 ignores these files; the Workshop workspace serves the desk there.
"""

import datetime
import json
import os
import re

# ───────────────────────────── SPEC ─────────────────────────────
SPEC = {
	"app": "armak",
	"app_title": "Armak",  # must match hooks.app_title
	"logo": "/assets/armak/images/armak-logo.svg",
	"tiles": [
		{"label": "Armak", "link": "auto"},  # "auto" → first sidebar URL
	],
	"rail": [
		{
			"title": "Workshop",  # = module name
			"module": "Workshop",
			"icon": "wrench",
			"items": [
				("workspace", "Home", "Workshop", "home"),
				("page", "Workshop Board", "workshop-board", "layout-dashboard"),
				("doctype", "Repair Order", "Repair Order", "clipboard-list"),
				("doctype", "Gun", "Gun", "crosshair"),
				("doctype", "Customer", "Customer", "users"),
				(
					"section",
					"Billing",
					"receipt",
					[
						("doctype", "Sales Invoice", "Sales Invoice"),
						("doctype", "Payment Entry", "Payment Entry"),
					],
				),
				(
					"section",
					"Production",
					"scissors",
					[
						("doctype", "Production Entry", "Production Entry"),
						("doctype", "Material Templates (BOM)", "BOM"),
					],
				),
				(
					"section",
					"Stock",
					"package",
					[
						("doctype", "Stock Entries", "Stock Entry"),
						("doctype", "Item", "Item"),
						("doctype", "Material Request", "Material Request"),
					],
				),
			],
		},
		{
			"title": "Workshop Reports",
			"module": "Workshop",
			"icon": "chart-column",
			"items": [
				("report", "Profit per Job", "Repair Order Profit", "chart-column"),
				("report", "Material Consumption", "Workshop Material Consumption", "package"),
				("report", "Production per Month", "Workshop Production", "scissors"),
				(
					"section",
					"Sales & Collections",
					"wallet",
					[
						("report", "Sales Register", "Sales Register"),
						("report", "Accounts Receivable", "Accounts Receivable"),
					],
				),
				(
					"section",
					"Stock",
					"warehouse",
					[
						("report", "Stock Balance", "Stock Balance"),
						("report", "Stock Projected Qty", "Stock Projected Qty"),
					],
				),
			],
		},
		{
			"title": "Workshop Setup",
			"module": "Workshop",
			"icon": "settings",
			"items": [
				("doctype", "Workshop Settings", "Workshop Settings", "settings"),
				("doctype", "Material Templates", "Service Material Template", "list-checks"),
				("doctype", "Item Price", "Item Price", "tag"),
				("doctype", "Branch", "Branch", "git-branch"),
				("doctype", "Mode of Payment", "Mode of Payment", "banknote"),
			],
		},
	],
}
# ────────────────────────────────────────────────────────────────

NOW = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
ROOT = SPEC["app"]


def scrub(s):
	return s.replace(" ", "_").replace("-", "_").lower()


def slug(s):
	return re.sub(r"\s+", "-", s.lower().replace("&", " and ").strip())


FLAGS = {
	"added": 0,
	"child": 0,
	"collapsible": 1,
	"hidden": 0,
	"indent": 0,
	"is_default_module": 0,
	"keep_closed": 0,
	"open_in_new_tab": 0,
	"show_arrow": 0,
}
TYPES = {
	"doctype": "DocType",
	"report": "Report",
	"workspace": "Workspace",
	"page": "Page",
	"dashboard": "Dashboard",
}


def meta(doctype, name):
	return {
		"app": SPEC["app"],
		"creation": NOW,
		"modified": NOW,
		"docstatus": 0,
		"idx": 0,
		"doctype": doctype,
		"name": name,
		"owner": "Administrator",
		"modified_by": "Administrator",
		"standard": 1,
	}


def dump(path, doc):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	# developer CLI, not a web endpoint: paths come from the SPEC above, inside the repo
	with open(path, "w") as f:  # nosemgrep: frappe-security-file-traversal
		f.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")
	print("wrote", path)


def link(kind, label, target, icon=None, child=0):
	row = {**FLAGS, "type": "Link", "label": label, "child": child}
	if kind == "url":
		row.update(link_type="URL", url=target)
	else:
		row.update(link_type=TYPES[kind], link_to=target)
	if icon:
		row["icon"] = icon
	return row


def rows(items):
	out = []
	for it in items:
		if it[0] == "section":
			_, label, icon, children = it
			out.append(
				{
					**FLAGS,
					"type": "Section Break",
					"label": label,
					"icon": icon,
					"link_type": "DocType",
					"indent": 1,
					"keep_closed": 1,
				}
			)
			out += [link(*c, child=1) for c in children]
		else:
			out.append(link(*it))
	return [
		{"doctype": "Sidebar Item", "parentfield": "items", "parenttype": "Sidebar", "idx": i, **r}
		for i, r in enumerate(out, 1)
	]


def main():
	bad = [r["title"] for r in SPEC["rail"] if re.search(r"[/?#%\\]", r["title"])]
	assert not bad, f"unroutable characters in titles: {bad}"
	assert len({slug(r["title"]) for r in SPEC["rail"]}) == len(SPEC["rail"]), "duplicate slugs"

	for r in SPEC["rail"]:
		doc = meta("Sidebar", r["title"])
		doc.update(title=r["title"], module=r["module"], header_icon=r["icon"], items=rows(r["items"]))
		s = scrub(r["title"])
		dump(f"{ROOT}/{scrub(r['module'])}/sidebar/{s}/{s}.json", doc)

	dock = meta("Dock", SPEC["app"])
	dock.update(
		user="",
		items=[
			{
				"added": 0,
				"hidden": 0,
				"icon": r["icon"],
				"link_type": "Sidebar",
				"link_to": r["title"],
				"title": r["title"],
			}
			for r in SPEC["rail"]
		],
	)
	dump(f"{ROOT}/dock/{SPEC['app']}/{SPEC['app']}.json", dock)

	first_url = "/desk/" + slug(SPEC["rail"][0]["title"])
	for n, t in enumerate(SPEC["tiles"]):
		tile = meta("Desktop Icon", t["label"])
		tile.update(
			label=t["label"],
			icon_type="App",
			link_type="External",
			hidden=0,
			idx=20 + n,
			link=first_url if t["link"] == "auto" else t["link"],
			logo_url=t.get("logo", SPEC["logo"]),
			roles=[],
		)
		dump(f"{ROOT}/desktop_icon/{scrub(t['label'])}.json", tile)

	print(f"\nSet hooks.add_to_apps_screen route to: {first_url}")


if __name__ == "__main__":
	main()
