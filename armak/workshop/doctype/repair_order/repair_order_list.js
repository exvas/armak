const STATUS_COLOR = {
	Draft: "red",
	Received: "blue",
	"In Progress": "orange",
	"Ready for Delivery": "purple",
	Delivered: "green",
	Cancelled: "gray",
};

frappe.listview_settings["Repair Order"] = {
	add_fields: ["status", "expected_delivery"],
	get_indicator(doc) {
		const late =
			["Received", "In Progress"].includes(doc.status) &&
			doc.expected_delivery &&
			frappe.datetime.str_to_obj(doc.expected_delivery) < new Date();
		if (late) return [__("Late"), "red", "status,in,Received,In Progress"];
		return [__(doc.status), STATUS_COLOR[doc.status], "status,=," + doc.status];
	},
};
