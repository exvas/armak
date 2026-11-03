# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from armak.workshop.booking import book, cancel, system_booking
from armak.workshop.doctype.workshop_settings.workshop_settings import get_branch_settings


class ProductionEntry(Document):
	def validate(self):
		self.set_defaults()
		self.validate_bom()
		if not self.materials:
			self.set_bom_materials()
		for row in self.materials:
			if flt(row.qty) <= 0:
				frappe.throw(_("Materials row {0}: quantity must be more than zero").format(row.idx))
			if row.item_code == self.item_code:
				frappe.throw(_("Materials row {0}: the product cannot be its own material").format(row.idx))

	def on_submit(self):
		with system_booking() as user:
			stock_entry = self.make_stock_entry(user)
		cost = sum(flt(d.amount) for d in stock_entry.items if not d.is_finished_item)
		self.db_set(
			{
				"stock_entry": stock_entry.name,
				"material_cost": cost,
				"unit_cost": cost / flt(self.qty) if flt(self.qty) else 0,
			}
		)

	def on_cancel(self):
		if self.stock_entry:
			with system_booking():
				cancel("Stock Entry", self.stock_entry)

	def set_defaults(self):
		branch = get_branch_settings(self.branch) if self.branch else None
		if branch:
			if self.company != branch.company:
				frappe.throw(_("Branch {0} belongs to {1}").format(self.branch, branch.company))
			self.source_warehouse = self.source_warehouse or branch.production_warehouse
			self.target_warehouse = self.target_warehouse or branch.finished_goods_warehouse
		if not self.bom and self.item_code:
			self.bom = get_default_bom(self.item_code)

	def validate_bom(self):
		bom = frappe.db.get_value("BOM", self.bom, ["item", "is_active", "docstatus"], as_dict=True)
		if not bom or bom.docstatus != 1 or not bom.is_active:
			frappe.throw(_("Material template {0} is not an active, submitted BOM").format(self.bom))
		if bom.item != self.item_code:
			frappe.throw(
				_("Material template {0} is for {1}, not {2}").format(self.bom, bom.item, self.item_code)
			)

	def set_bom_materials(self):
		for row in get_bom_materials(self.bom, self.qty):
			self.append("materials", row)

	def make_stock_entry(self, user):
		"""One Manufacture entry: the materials out of production stock, the products into the showroom.

		Built without `from_bom`, so it records the quantities really used rather than the BOM's.
		"""
		branch = get_branch_settings(self.branch)
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Manufacture"
		se.purpose = "Manufacture"
		se.company = self.company
		se.posting_date = self.posting_date
		se.set_posting_time = 1
		se.from_bom = 0
		se.remarks = _("Production Entry {0}: {1} x {2}").format(self.name, self.qty, self.item_name)
		cost_center = branch.cost_center if branch else None
		for row in self.materials:
			se.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"s_warehouse": self.source_warehouse,
					"cost_center": cost_center,
				},
			)
		se.append(
			"items",
			{
				"item_code": self.item_code,
				"qty": self.qty,
				"t_warehouse": self.target_warehouse,
				"is_finished_item": 1,
				"cost_center": cost_center,
			},
		)
		se.armak_production_entry = self.name
		if se.meta.has_field("branch"):
			se.branch = self.branch
		return book(se, user)


def get_default_bom(item_code):
	return frappe.db.get_value("BOM", {"item": item_code, "is_default": 1, "is_active": 1, "docstatus": 1})


@frappe.whitelist()
def get_bom_materials(bom: str, qty: float):
	"""Materials of `bom` for making `qty` products, in stock UOM."""
	frappe.has_permission("Production Entry", "create", throw=True)
	doc = frappe.get_cached_doc("BOM", bom)
	factor = flt(qty) / flt(doc.quantity or 1)
	precision = frappe.get_precision("Production Entry Material", "qty")
	return [
		{
			"item_code": row.item_code,
			"item_name": row.item_name,
			"uom": row.stock_uom,
			"qty": flt(flt(row.stock_qty) * factor, precision),
			"bom_qty": flt(flt(row.stock_qty) * factor, precision),
		}
		for row in doc.items
	]


@frappe.whitelist()
def get_product_bom(item_code: str):
	frappe.has_permission("Production Entry", "create", throw=True)
	return get_default_bom(item_code)


@frappe.whitelist()
def get_branch_defaults(branch: str):
	"""Company and production warehouses of `branch`, for the form."""
	frappe.has_permission("Production Entry", "create", throw=True)
	row = get_branch_settings(branch)
	if not row:
		return {}
	return {
		"company": row.company,
		"source_warehouse": row.production_warehouse,
		"target_warehouse": row.finished_goods_warehouse,
	}
