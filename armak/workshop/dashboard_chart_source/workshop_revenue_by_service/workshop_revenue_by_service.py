import frappe
from frappe.utils import add_months, get_first_day, get_year_start, nowdate
from frappe.utils.dashboard import cache_source

PERIOD_START = {
	"This Month": lambda today: get_first_day(today),
	"Last 3 Months": lambda today: get_first_day(add_months(today, -2)),
	"This Year": lambda today: get_year_start(today),
}


@frappe.whitelist()
@cache_source
def get(
	chart_name: str | None = None,
	chart: str | dict | None = None,
	no_cache: int | bool | None = None,
	filters: str | dict | list | None = None,
	from_date: str | None = None,
	to_date: str | None = None,
	timespan: str | None = None,
	time_interval: str | None = None,
	heatmap_year: str | int | None = None,
):
	"""Service revenue (excl. VAT) of orders delivered in the period, largest first."""
	frappe.has_permission("Repair Order", throw=True)
	filters = frappe.parse_json(filters) or {}
	start = PERIOD_START.get(filters.get("period"), PERIOD_START["This Month"])(nowdate())
	conditions = {"docstatus": 1, "status": "Delivered", "delivered_on": (">=", start)}
	if filters.get("branch"):
		conditions["branch"] = filters["branch"]
	orders = frappe.get_list("Repair Order", filters=conditions, pluck="name", limit_page_length=0)
	totals = {}
	if orders:
		for row in frappe.get_all(
			"Repair Order Service",
			filters={"parent": ("in", orders), "parenttype": "Repair Order"},
			fields=["item_name", "service_item", "amount"],
		):
			label = row.item_name or row.service_item
			totals[label] = totals.get(label, 0) + (row.amount or 0)
	ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
	return {
		"labels": [label for label, _ in ranked],
		"datasets": [{"name": "Revenue", "values": [value for _, value in ranked]}],
	}
