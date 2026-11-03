"""Jinja helpers for the Workshop print formats."""

import base64
from io import BytesIO

import pyqrcode


def qr_data_uri(text, scale=4):
	"""PNG QR code of `text` as a data URI, made locally so printing works offline."""
	buffer = BytesIO()
	pyqrcode.create(str(text)).png(buffer, scale=scale)
	return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()
