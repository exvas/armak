# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	return get_columns(), rows, None, get_chart(rows), get_summary(rows)


def get_columns():
	return [
		{
			"label": _("Repair Order"),
			"fieldname": "name",
			"fieldtype": "Link",
			"options": "Repair Order",
			"width": 140,
		},
		{"label": _("Delivered On"), "fieldname": "delivered_on", "fieldtype": "Date", "width": 105},
		{"label": _("Branch"), "fieldname": "branch", "fieldtype": "Link", "options": "Branch", "width": 130},
		{"label": _("Customer"), "fieldname": "customer_name", "fieldtype": "Data", "width": 170},
		{"label": _("Gun"), "fieldname": "gun", "fieldtype": "Link", "options": "Gun", "width": 120},
		{"label": _("Services"), "fieldname": "services", "fieldtype": "Data", "width": 220},
		{"label": _("Revenue (excl. VAT)"), "fieldname": "revenue", "fieldtype": "Currency", "width": 130},
		{"label": _("Material Cost"), "fieldname": "material_cost", "fieldtype": "Currency", "width": 120},
		{"label": _("Profit"), "fieldname": "profit", "fieldtype": "Currency", "width": 120},
		{"label": _("Margin %"), "fieldname": "margin", "fieldtype": "Percent", "width": 90},
		{
			"label": _("Sales Invoice"),
			"fieldname": "sales_invoice",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 140,
		},
	]


def get_rows(filters):
	conditions = {"docstatus": 1, "status": "Delivered"}
	if filters.company:
		conditions["company"] = filters.company
	if filters.branch:
		conditions["branch"] = filters.branch
	if filters.from_date and filters.to_date:
		conditions["delivered_on"] = ("between", [getdate(filters.from_date), add_days(filters.to_date, 1)])
	orders = frappe.get_list(
		"Repair Order",
		filters=conditions,
		fields=[
			"name",
			"delivered_on",
			"branch",
			"customer_name",
			"gun",
			"total",
			"material_cost",
			"profit",
			"sales_invoice",
		],
		order_by="delivered_on desc",
		limit_page_length=0,
	)
	services = {}
	if orders:
		for row in frappe.get_all(
			"Repair Order Service",
			filters={"parent": ("in", [o.name for o in orders]), "parenttype": "Repair Order"},
			fields=["parent", "item_name", "service_item"],
			order_by="idx",
		):
			services.setdefault(row.parent, []).append(row.item_name or row.service_item)
	for order in orders:
		order.services = ", ".join(services.get(order.name, []))
		order.revenue = flt(order.total)
		order.delivered_on = getdate(order.delivered_on)
		order.margin = flt(order.profit) / order.revenue * 100 if order.revenue else 0
	return orders


def get_chart(rows):
	by_month = {}
	for row in sorted(rows, key=lambda r: r.delivered_on):
		key = row.delivered_on.strftime("%b %Y")
		revenue, cost = by_month.get(key, (0, 0))
		by_month[key] = (revenue + row.revenue, cost + flt(row.material_cost))
	return {
		"data": {
			"labels": list(by_month),
			"datasets": [
				{"name": _("Revenue"), "values": [v[0] for v in by_month.values()]},
				{"name": _("Material Cost"), "values": [v[1] for v in by_month.values()]},
			],
		},
		"type": "bar",
		"fieldtype": "Currency",
	}


def get_summary(rows):
	revenue = sum(r.revenue for r in rows)
	cost = sum(flt(r.material_cost) for r in rows)
	profit = revenue - cost
	return [
		{"label": _("Jobs Delivered"), "value": len(rows), "datatype": "Int", "indicator": "blue"},
		{"label": _("Revenue"), "value": revenue, "datatype": "Currency", "indicator": "blue"},
		{"label": _("Material Cost"), "value": cost, "datatype": "Currency", "indicator": "orange"},
		{
			"label": _("Profit"),
			"value": profit,
			"datatype": "Currency",
			"indicator": "green" if profit >= 0 else "red",
		},
		{
			"label": _("Margin"),
			"value": f"{(profit / revenue * 100) if revenue else 0:.1f}%",
			"datatype": "Data",
			"indicator": "green",
		},
	]
