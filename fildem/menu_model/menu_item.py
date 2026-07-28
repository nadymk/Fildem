#!/usr/bin/python3

import dbus


def clean_label(label):
	label = str(label or '')
	label = label.replace('__', '\0').replace('_', '').replace('\0', '_')
	label = label.replace('&&', '\0').replace('&', '').replace('\0', '&')
	return label


def format_label(parts):
	separator = u'\u0020\u0020\u00BB\u0020\u0020'
	return separator.join(parts)


def stringify_variant(value):
	try:
		if isinstance(value, (dbus.String, dbus.ObjectPath, dbus.Signature)):
			return str(value)
		if isinstance(value, dbus.Boolean):
			return bool(value)
		if isinstance(value, (dbus.Byte, dbus.Int16, dbus.Int32, dbus.Int64,
				dbus.UInt16, dbus.UInt32, dbus.UInt64)):
			return int(value)
		if isinstance(value, dbus.Double):
			return float(value)
		if isinstance(value, (dbus.Array, list, tuple)):
			return [stringify_variant(item) for item in value]
		if isinstance(value, (dbus.Dictionary, dict)):
			return {str(key): stringify_variant(item) for key, item in value.items()}
	except Exception:
		pass
	return value


def first_string(*values):
	for value in values:
		value = stringify_variant(value)
		if isinstance(value, str) and value:
			return value
		if isinstance(value, dict):
			for key in ('name', 'icon-name', 'names'):
				nested = first_string(value.get(key))
				if nested:
					return nested
		if isinstance(value, list):
			nested = first_string(*value)
			if nested:
				return nested
	return ''


def _coerce_bool(value):
	value = stringify_variant(value)
	if isinstance(value, bool):
		return value
	if isinstance(value, (int, float)):
		return bool(value)
	if isinstance(value, str):
		return value.strip().lower() not in ('', '0', 'false', 'none', 'null')
	return bool(value)


def deep_lookup(value, keys):
	value = stringify_variant(value)
	if isinstance(value, dict):
		for key in keys:
			if key in value:
				candidate = stringify_variant(value.get(key))
				if candidate not in ('', None, [], {}):
					return candidate
		for nested in value.values():
			candidate = deep_lookup(nested, keys)
			if candidate not in ('', None, [], {}):
				return candidate
	elif isinstance(value, list):
		for nested in value:
			candidate = deep_lookup(nested, keys)
			if candidate not in ('', None, [], {}):
				return candidate
	elif isinstance(value, tuple):
		for nested in value:
			candidate = deep_lookup(nested, keys)
			if candidate not in ('', None, [], {}):
				return candidate
	return None


def format_accelerator(accel):
	accel = stringify_variant(accel)
	if not accel:
		return ''
	if isinstance(accel, str):
		return accel
	if isinstance(accel, list):
		# GTK GMenuModel usually provides shortcuts as an array of arrays, e.g.
		# [["<Control>", "S"]] or [["Control", "S"]].
		if accel and isinstance(accel[0], list):
			accel = accel[0]
		return ''.join(
			'<' + str(part) + '>' if index != len(accel) - 1 else str(part)
			for index, part in enumerate(accel)
		)
	return str(accel)


class DbusGtkMenuItem(object):

	def __init__(self, item, path=[], enabled=True):
		self.path = path
		self.separator = False
		self.action = str(item.get('action', ''))
		self.accel = str(item.get('accel', '')) # <Primary><Shift><Alt>p
		self.shortcut = format_accelerator(item.get('shortcut', ''))
		self.label = clean_label(item.get('label', ''))
		self.text = format_label(self.path + [self.label])
		self.enabled = enabled
		self.toggle_type = ''
		self.toggle_state = False
		self.icon_name = first_string(deep_lookup(item, (
			'icon-name',
			'verb-icon',
			'icon',
			'stock-id',
		)))
		self.icon_data = stringify_variant(deep_lookup(item, ('icon-data', 'icon_data')) or [])
		self.toggle_type = str(deep_lookup(item, ('toggle-type', 'toggle_type')) or '')
		self.toggle_state = _coerce_bool(deep_lookup(item, ('toggle-state', 'toggle_state')))
		if not self.toggle_type and _coerce_bool(deep_lookup(item, ('toggle',))):
			self.toggle_type = 'checkmark'
			self.toggle_state = True
		# :submenu
		# two index that indicate the group
		# dbus.String(':submenu'): dbus.Struct((dbus.UInt32(11), dbus.UInt32(0))
		# used for separators and radio button groups
		self.section = None

	def set_toggle(self, toggle):
		if not len(toggle):
			return
		toggle = toggle[0]
		if isinstance(toggle, dbus.Boolean):
			self.toggle_type = 'checkmark'
			self.toggle_state = bool(toggle)
		elif isinstance(toggle, str):
			self.toggle_type = 'radio'
			self.toggle_state = len(toggle) > 0

	def set_description(self, desc):
		if desc is None:
			return
		self.enabled = desc[0]
		self.toggle_state = desc[1]

class DbusAppMenuItem(object):

	def __init__(self, item, path=[]):
		self.path  = path
		self.action = int(item[0])
		self.accel = self.get_shorcut(item[1])
		self.separator = item[1].get('type', '') == 'separator'
		self.label = clean_label(item[1].get('label', ''))
		self.text = format_label(self.path + [self.label])
		self.enabled = item[1].get('enabled', True)
		self.visible = item[1].get('visible', True)
		self.toggle_state = item[1].get('toggle-state', 0) == 1
		self.toggle_type = item[1].get('toggle-type', '') # 'radio' or 'checkmark'
		self.icon_name = first_string(
			item[1].get('icon-name', ''),
			item[1].get('icon', ''),
			item[1].get('stock-id', ''),
		)
		self.icon_data = stringify_variant(item[1].get('icon-data', item[1].get('icon_data', [])))
		# Only used on Gtkapps
		self.section = None
		self.children = []

	def get_shorcut(self, item):
		return format_accelerator(item.get('shortcut', ''))

	def update_props(self, props):
		if 'children-display' in props:
			return
		self.enabled = props.get('enabled', self.enabled)
		self.label = clean_label(props.get('label', self.label))
		self.toggle_state = _coerce_bool(props.get('toggle-state', self.toggle_state))
		self.toggle_type = str(props.get('toggle-type', self.toggle_type) or self.toggle_type)
		self.icon_name = first_string(
			deep_lookup(props, ('icon-name', 'verb-icon', 'icon', 'stock-id')),
			self.icon_name,
		)
		self.icon_data = stringify_variant(
			deep_lookup(props, ('icon-data', 'icon_data')) or self.icon_data
		)
		self.visible = props.get('visible', self.visible)
