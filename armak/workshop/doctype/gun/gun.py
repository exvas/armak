# Copyright (c) 2026, sammish and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class Gun(Document):
	def before_insert(self):
		# gun numbers are typed from the gun itself; keep one spelling so search and history match.
		# before_insert runs before naming, so the name gets the same spelling
		self.gun_number = " ".join((self.gun_number or "").split()).upper()
