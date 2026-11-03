# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	return get_columns(), rows, None, get_chart(rows)


def get_columns():
	return [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 100},
		{
			"label": _("Product"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{"label": _("Product Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 200},
		{"label": _("Qty Made"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("Material Cost"), "fieldname": "material_cost", "fieldtype": "Currency", "width": 130},
		{"label": _("Cost per Unit"), "fieldname": "unit_cost", "fieldtype": "Currency", "width": 120},
		{"label": _("Batches"), "fieldname": "batches", "fieldtype": "Int", "width": 80},
	]


def get_rows(filters):
	conditions = {"docstatus": 1}
	if filters.company:
		conditions["company"] = filters.company
	if filters.branch:
		conditions["branch"] = filters.branch
	if filters.item_code:
		conditions["item_code"] = filters.item_code
	if filters.from_date and filters.to_date:
		conditions["posting_date"] = ("between", [filters.from_date, filters.to_date])
	# material cost is permlevel 1: get_list leaves it out for users who may not see costs
	entries = frappe.get_list(
		"Production Entry",
		filters=conditions,
		fields=["posting_date", "item_code", "item_name", "uom", "qty", "material_cost"],
		order_by="posting_date",
		limit_page_length=0,
	)
	grouped = {}
	for e in entries:
		month = getdate(e.posting_date).strftime("%Y-%m")
		row = grouped.setdefault(
			(month, e.item_code),
			frappe._dict(
				month=month,
				item_code=e.item_code,
				item_name=e.item_name,
				uom=e.uom,
				qty=0,
				material_cost=0,
				batches=0,
			),
		)
		row.qty += flt(e.qty)
		row.material_cost += flt(e.get("material_cost"))
		row.batches += 1
	rows = sorted(grouped.values(), key=lambda r: (r.month, r.item_name or ""))
	for row in rows:
		row.unit_cost = row.material_cost / row.qty if row.qty else 0
	return rows


def get_chart(rows):
	by_month = {}
	for row in rows:
		by_month[row.month] = by_month.get(row.month, 0) + row.qty
	return {
		"data": {
			"labels": list(by_month),
			"datasets": [{"name": _("Products Made"), "values": list(by_month.values())}],
		},
		"type": "bar",
	}
