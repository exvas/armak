# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Sum
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	return get_columns(), rows, None, get_chart(rows)


def get_columns():
	return [
		{"label": _("Month"), "fieldname": "month", "fieldtype": "Data", "width": 100},
		{
			"label": _("Material"),
			"fieldname": "item_code",
			"fieldtype": "Link",
			"options": "Item",
			"width": 160,
		},
		{"label": _("Material Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Qty Used"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("Cost"), "fieldname": "amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Repair Orders"), "fieldname": "orders", "fieldtype": "Int", "width": 110},
	]


def get_rows(filters):
	frappe.has_permission("Stock Entry", throw=True)
	se = frappe.qb.DocType("Stock Entry")
	sed = frappe.qb.DocType("Stock Entry Detail")
	month = frappe.qb.functions("DATE_FORMAT", se.posting_date, "%Y-%m")
	query = (
		frappe.qb.from_(sed)
		.join(se)
		.on(se.name == sed.parent)
		.select(
			month.as_("month"),
			sed.item_code,
			sed.item_name,
			sed.stock_uom.as_("uom"),
			Sum(sed.transfer_qty).as_("qty"),
			Sum(sed.amount).as_("amount"),
			Count(se.armak_repair_order).distinct().as_("orders"),
		)
		.where(
			(se.docstatus == 1)
			& (se.armak_repair_order.isnotnull())
			& (se.posting_date[filters.from_date : filters.to_date])
		)
		.groupby(month, sed.item_code, sed.item_name, sed.stock_uom)
		.orderby(month)
		.orderby(sed.item_name)
	)
	if filters.company:
		query = query.where(se.company == filters.company)
	if filters.item_code:
		query = query.where(sed.item_code == filters.item_code)
	if filters.branch and frappe.get_meta("Stock Entry").has_field("branch"):
		query = query.where(se.branch == filters.branch)
	return query.run(as_dict=True)


def get_chart(rows):
	"""Cost of the materials used per month."""
	by_month = {}
	for row in rows:
		by_month[row.month] = by_month.get(row.month, 0) + flt(row.amount)
	return {
		"data": {
			"labels": list(by_month),
			"datasets": [{"name": _("Material Cost"), "values": list(by_month.values())}],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}
