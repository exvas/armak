# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account
from erpnext.accounts.party import get_party_account
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, get_datetime, now_datetime, nowdate

from armak.workshop.doctype.workshop_settings.workshop_settings import get_branch_settings

# status -> statuses it may move to by a button on the submitted order
NEXT_STATUS = {
	"Received": ("In Progress", "Ready for Delivery"),
	"In Progress": ("Ready for Delivery",),
	"Ready for Delivery": ("In Progress", "Delivered"),
}


class RepairOrder(Document):
	def validate(self):
		self.set_customer_from_gun()
		self.set_defaults()
		self.set_service_rates()
		self.calculate_totals()
		if self.docstatus == 0:
			self.status = "Draft"
			if not any(row.from_template for row in self.materials):
				self.set_template_materials()
		self.validate_materials()

	def before_update_after_submit(self):
		self.validate_materials()

	def on_submit(self):
		self.db_set("status", "Received")
		self.update_advance()

	def before_cancel(self):
		if self.sales_invoice and frappe.db.get_value("Sales Invoice", self.sales_invoice, "docstatus") == 1:
			frappe.throw(_("Cancel Sales Invoice {0} first").format(self.sales_invoice))

	def on_cancel(self):
		if self.stock_entry and frappe.db.get_value("Stock Entry", self.stock_entry, "docstatus") == 1:
			frappe.get_doc("Stock Entry", self.stock_entry).cancel()
		self.db_set("status", "Cancelled")

	# ------------------------------------------------------------ validate helpers

	def set_customer_from_gun(self):
		if not self.gun:
			return
		owner = frappe.db.get_value("Gun", self.gun, "customer")
		if not self.customer:
			self.customer = owner
		elif owner != self.customer:
			frappe.msgprint(
				_("Gun {0} is registered to {1}, not {2}").format(self.gun, owner, self.customer),
				indicator="orange",
				alert=True,
			)
		# fetch_from ran before validate, so a customer taken from the gun has no details yet
		if self.customer and self.docstatus == 0:
			details = frappe.db.get_value(
				"Customer", self.customer, ["customer_name", "mobile_no", "armak_civil_id"], as_dict=True
			)
			self.customer_name = details.customer_name
			self.mobile_no = details.mobile_no
			self.civil_id = details.armak_civil_id

	def set_defaults(self):
		branch = get_branch_settings(self.branch) if self.branch else None
		if branch and self.company != branch.company:
			frappe.throw(_("Branch {0} belongs to {1}").format(self.branch, branch.company))
		if not self.expected_delivery:
			days = frappe.db.get_single_value("Workshop Settings", "default_delivery_days") or 0
			self.expected_delivery = get_datetime(add_days(self.posting_date or nowdate(), days))
		if not self.taxes_and_charges:
			self.taxes_and_charges = (
				frappe.db.get_value(
					"Sales Taxes and Charges Template",
					{"is_default": 1, "company": self.company, "disabled": 0},
				)
				or None
			)

	def set_service_rates(self):
		price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list")
		for row in self.services:
			if not row.rate and price_list:
				row.rate = get_service_rate(row.service_item, price_list)
			row.amount = flt(row.qty) * flt(row.rate)

	def calculate_totals(self):
		self.total = sum(flt(row.amount) for row in self.services)
		rate = 0
		if self.taxes_and_charges:
			rate = sum(
				flt(tax.rate)
				for tax in frappe.get_all(
					"Sales Taxes and Charges",
					filters={
						"parent": self.taxes_and_charges,
						"parenttype": "Sales Taxes and Charges Template",
					},
					fields=["rate", "charge_type"],
				)
				if tax.charge_type == "On Net Total"
			)
		self.tax_amount = flt(self.total * rate / 100, self.precision("tax_amount"))
		self.grand_total = flt(self.total + self.tax_amount, self.precision("grand_total"))
		self.balance = flt(self.grand_total - flt(self.advance_paid), self.precision("balance"))

	def set_template_materials(self):
		"""Add the template materials of every service that has none on the order yet."""
		covered = {row.for_service for row in self.materials if row.from_template}
		rows = []
		for service in self.services:
			if service.service_item in covered:
				continue
			template = frappe.db.get_value(
				"Service Material Template", {"service_item": service.service_item, "disabled": 0}
			)
			if not template:
				continue
			for item in frappe.get_doc("Service Material Template", template).items:
				rows.append(
					{
						"item_code": item.item_code,
						"item_name": item.item_name,
						"uom": item.uom,
						"qty": flt(item.qty) * flt(service.qty),
						"from_template": 1,
						"for_service": service.service_item,
					},
				)
			covered.add(service.service_item)
		for row in rows:
			self.append("materials", row)

	def validate_materials(self):
		before = self.get_doc_before_save()
		if before and before.stock_entry and _material_rows(before) != _material_rows(self):
			frappe.throw(_("Materials were already issued in {0}").format(before.stock_entry))
		for row in self.materials:
			if flt(row.qty) <= 0:
				frappe.throw(_("Materials row {0}: quantity must be more than zero").format(row.idx))

	# ------------------------------------------------------------ workflow

	def _move_to(self, status):
		if status not in NEXT_STATUS.get(self.status, ()):
			frappe.throw(_("A {0} order cannot be moved to {1}").format(self.status, status))

	@frappe.whitelist()
	def start_work(self, technician: str | None = None):
		self.check_permission("write")
		self._move_to("In Progress")
		if technician:
			self.technician = technician
		self.status = "In Progress"
		self.save()

	@frappe.whitelist()
	def mark_ready(self):
		"""Issue the materials from the branch warehouse and set Ready for Delivery."""
		self.check_permission("write")
		self._move_to("Ready for Delivery")
		if self.materials and not self.stock_entry:
			stock_entry = self.make_material_issue()
			self.stock_entry = stock_entry.name
			self.material_cost = stock_entry.total_outgoing_value
		self.status = "Ready for Delivery"
		self.save()
		return self.stock_entry

	@frappe.whitelist()
	def receive_advance(self, amount: float, mode_of_payment: str):
		"""Book a customer advance for this order (allocated to its invoice on delivery)."""
		self.check_permission("write")
		if self.status in ("Delivered", "Cancelled") or self.docstatus != 1:
			frappe.throw(_("Advances can only be taken on an open, submitted order"))
		amount = flt(amount)
		if amount <= 0:
			frappe.throw(_("Advance amount must be more than zero"))
		payment = make_advance_payment(self, amount, mode_of_payment)
		self.update_advance()
		return payment.name

	@frappe.whitelist()
	def deliver(self, mode_of_payment: str | None = None, amount_paid: float = 0):
		"""Hand the gun back: invoice the services (advances allocated) and take the balance."""
		self.check_permission("write")
		self._move_to("Delivered")
		invoice = self.make_sales_invoice()
		amount_paid = flt(amount_paid)
		if amount_paid > 0:
			if not mode_of_payment:
				frappe.throw(_("Select the mode of payment for the balance"))
			pe = get_payment_entry("Sales Invoice", invoice.name)
			pe.mode_of_payment = mode_of_payment
			pe.paid_to = get_bank_cash_account(mode_of_payment, self.company)["account"]
			pe.paid_amount = pe.received_amount = min(amount_paid, flt(invoice.outstanding_amount))
			pe.references[0].allocated_amount = pe.paid_amount
			pe.reference_no = pe.reference_no or invoice.name
			pe.reference_date = pe.reference_date or nowdate()
			self._tag(pe)
			pe.armak_payment_stage = "Balance"
			pe.insert()
			pe.submit()
		self.sales_invoice = invoice.name
		self.delivered_on = now_datetime()
		self.profit = flt(invoice.base_net_total) - flt(self.material_cost)
		self.status = "Delivered"
		self.save()
		self.update_advance()
		return invoice.name

	# ------------------------------------------------------------ documents

	def _tag(self, doc):
		"""Link a generated document back to this order and its branch / cost center."""
		doc.armak_repair_order = self.name
		if doc.meta.has_field("branch"):
			doc.branch = self.branch
		branch = get_branch_settings(self.branch)
		if branch and branch.cost_center and doc.meta.has_field("cost_center"):
			doc.cost_center = branch.cost_center
		return branch

	def make_material_issue(self):
		branch = get_branch_settings(self.branch)
		if not branch:
			frappe.throw(
				_("Set the materials warehouse of branch {0} in Workshop Settings").format(self.branch)
			)
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Issue"
		se.purpose = "Material Issue"
		se.company = self.company
		se.posting_date = nowdate()
		se.from_warehouse = branch.materials_warehouse
		se.remarks = _("Materials used on Repair Order {0} (gun {1})").format(self.name, self.gun)
		for row in self.materials:
			se.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": row.qty,
					"s_warehouse": branch.materials_warehouse,
					"cost_center": branch.cost_center,
				},
			)
		self._tag(se)
		se.insert()
		se.submit()
		return se

	def make_sales_invoice(self):
		branch = get_branch_settings(self.branch)
		si = frappe.new_doc("Sales Invoice")
		si.company = self.company
		si.customer = self.customer
		si.posting_date = nowdate()
		si.set_posting_time = 1
		si.due_date = nowdate()
		si.allocate_advances_automatically = 0
		si.update_stock = 0
		si.remarks = _("Repair Order {0}, gun {1}").format(self.name, self.gun)
		for row in self.services:
			si.append(
				"items",
				{
					"item_code": row.service_item,
					"description": row.description or row.item_name,
					"qty": row.qty,
					"rate": row.rate,
					"cost_center": branch.cost_center if branch else None,
				},
			)
		self._tag(si)
		si.set_missing_values()
		if self.taxes_and_charges:
			si.taxes_and_charges = self.taxes_and_charges
			si.set("taxes", get_taxes_and_charges("Sales Taxes and Charges Template", self.taxes_and_charges))
		for pe in get_advance_payments(self.name):
			si.append(
				"advances",
				{
					"reference_type": "Payment Entry",
					"reference_name": pe.name,
					"remarks": pe.remarks,
					"advance_amount": pe.unallocated_amount,
					"allocated_amount": pe.unallocated_amount,
					"ref_exchange_rate": 1,
				},
			)
		si.calculate_taxes_and_totals()
		# never allocate more advance than the invoice total
		remaining = flt(si.rounded_total or si.grand_total)
		for adv in si.advances:
			adv.allocated_amount = min(flt(adv.allocated_amount), remaining)
			remaining -= adv.allocated_amount
		si.set("advances", [adv for adv in si.advances if adv.allocated_amount > 0])
		si.insert()
		si.submit()
		return si

	def update_advance(self):
		advance = sum(flt(pe.paid_amount) for pe in get_advance_payments(self.name, unallocated_only=False))
		if self.sales_invoice:
			balance = frappe.db.get_value("Sales Invoice", self.sales_invoice, "outstanding_amount")
		else:
			balance = flt(self.grand_total) - advance
		self.db_set({"advance_paid": advance, "balance": balance})


def _material_rows(doc):
	return [(row.item_code, flt(row.qty)) for row in doc.materials]


def get_advance_payments(repair_order, unallocated_only=True):
	"""Submitted advances of an order; only those still unallocated unless `unallocated_only` is off."""
	filters = {"armak_repair_order": repair_order, "armak_payment_stage": "Advance", "docstatus": 1}
	if unallocated_only:
		filters["unallocated_amount"] = (">", 0)
	return frappe.get_all(
		"Payment Entry",
		filters=filters,
		fields=["name", "paid_amount", "unallocated_amount", "remarks"],
		order_by="posting_date, creation",
	)


def make_advance_payment(order, amount, mode_of_payment):
	account = get_bank_cash_account(mode_of_payment, order.company)["account"]
	pe = frappe.new_doc("Payment Entry")
	pe.payment_type = "Receive"
	pe.company = order.company
	pe.posting_date = nowdate()
	pe.mode_of_payment = mode_of_payment
	pe.party_type = "Customer"
	pe.party = order.customer
	pe.paid_from = get_party_account("Customer", order.customer, order.company)
	pe.paid_to = account
	pe.paid_amount = pe.received_amount = amount
	pe.source_exchange_rate = pe.target_exchange_rate = 1
	pe.reference_no = order.name
	pe.reference_date = nowdate()
	pe.remarks = _("Advance for Repair Order {0} (gun {1})").format(order.name, order.gun)
	order._tag(pe)
	pe.armak_payment_stage = "Advance"
	pe.setup_party_account_field()
	pe.set_missing_values()
	pe.insert()
	pe.submit()
	return pe


@frappe.whitelist()
def get_service_rate(item_code: str, price_list: str | None = None):
	price_list = price_list or frappe.db.get_single_value("Selling Settings", "selling_price_list")
	return flt(
		frappe.db.get_value(
			"Item Price", {"item_code": item_code, "price_list": price_list}, "price_list_rate"
		)
	)


@frappe.whitelist()
def get_branch_company(branch: str):
	row = get_branch_settings(branch)
	return row.company if row else None
