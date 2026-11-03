// Copyright (c) 2026, sammish and contributors
// For license information, please see license.txt

frappe.ui.form.on("Gun", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("New Repair Order"), () =>
			frappe.new_doc("Repair Order", { gun: frm.doc.name, customer: frm.doc.customer })
		);
	},
});
