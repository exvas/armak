"""Book the ledger documents a Repair Order or Production Entry makes.

Workshop staff have rights on their own documents, not on the ledgers behind them, and ERPNext
reads accounts, fiscal years and cost centers with the current user's rights while it builds an
invoice, payment or stock entry. The caller checks the user's right on its own document, then
builds and books the ledgers inside `system_booking()`; `book()` keeps the real user as owner.
"""

from contextlib import contextmanager

import frappe


@contextmanager
def system_booking():
	"""Run the block as Administrator and yield the real user."""
	user = frappe.session.user
	if user == "Administrator":
		yield user
		return
	# reviewed: callers check the user's right on their own document before entering, and the
	# real user is always restored, also when booking fails
	frappe.set_user("Administrator")  # nosemgrep: frappe-setuser
	try:
		yield user
	finally:
		frappe.set_user(user)  # nosemgrep: frappe-setuser


def book(doc, user):
	"""Insert and submit `doc`, owned by `user` for the audit trail."""
	doc.insert()
	doc.submit()
	if user != "Administrator":
		doc.db_set({"owner": user, "modified_by": user}, update_modified=False)
	return doc


def cancel(doctype, name):
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		doc.cancel()
