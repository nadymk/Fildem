import dbus
import dbus.service

from gi.repository import GLib

BUS_NAME = 'com.canonical.AppMenu.Registrar'
BUS_PATH = '/com/canonical/AppMenu/Registrar'
LOMIRI_BUS_NAME = 'com.lomiri.MenuRegistrar'
LOMIRI_BUS_PATH = '/com/lomiri/MenuRegistrar'


class AppMenuService(dbus.service.Object):
	"""
		Types:
			- u: int
			- a: array
			- y: byte
			- s: string
			- o: DBus object path
			- g: DBus type signature

		https://people.gnome.org/~ryanl/glib-docs/gvariant-format-strings.html
	"""
	def __init__(self):
		self.window_dict = dict()
		self.lomiri = LomiriMenuService()

		bus_name = dbus.service.BusName(BUS_NAME, bus=dbus.SessionBus())
		dbus.service.Object.__init__(self, bus_name, BUS_PATH)

	@dbus.service.method(BUS_NAME, in_signature='uo', sender_keyword='sender')
	def RegisterWindow(self, windowId, menuObjectPath, sender):
		print('Fildem Canonical app menu registered:', int(windowId), sender, menuObjectPath, flush=True)
		self.window_dict[windowId] = [dbus.String(sender), dbus.ObjectPath(menuObjectPath)]
		self.WindowRegistered(windowId, sender, menuObjectPath)

	@dbus.service.method(BUS_NAME, in_signature='u')
	def UnregisterWindow(self, windowId):
		print('Fildem Canonical app menu unregistered:', int(windowId), flush=True)
		if windowId in self.window_dict:
			del self.window_dict[windowId]
		self.WindowUnregistered(windowId)

	@dbus.service.signal(BUS_NAME, signature='uso')
	def WindowRegistered(self, windowId, sender, menuObjectPath):
		pass

	@dbus.service.signal(BUS_NAME, signature='u')
	def WindowUnregistered(self, windowId):
		pass

	@dbus.service.method(BUS_NAME, in_signature='u', out_signature='so')
	def GetMenuForWindow(self, windowId):
		if windowId in self.window_dict:
			return self.window_dict[windowId]

	@dbus.service.method(BUS_NAME, out_signature='a{u(so)}')
	def GetMenus(self):
		return self.window_dict

	@dbus.service.method(BUS_NAME)
	def Q(self):
		GLib.MainLoop().quit()


class LomiriMenuService(dbus.service.Object):
	def __init__(self):
		self.app_dict = dict()
		self.surface_dict = dict()
		self.bus = dbus.SessionBus()
		bus_name = dbus.service.BusName(LOMIRI_BUS_NAME, bus=self.bus)
		dbus.service.Object.__init__(self, bus_name, LOMIRI_BUS_PATH)

	def prune_dead_owners(self):
		def is_alive(entry):
			service_name = str(entry[0])
			try:
				return self.bus.name_has_owner(service_name)
			except Exception:
				return False

		self.app_dict = {pid: entry for pid, entry in self.app_dict.items() if is_alive(entry)}
		self.surface_dict = {surface: entry for surface, entry in self.surface_dict.items() if is_alive(entry)}

	@dbus.service.method(LOMIRI_BUS_NAME, in_signature='uoos', sender_keyword='sender')
	def RegisterAppMenu(self, pid, menuObjectPath, actionObjectPath, service, sender):
		self.prune_dead_owners()
		service_name = service or sender
		self.app_dict[int(pid)] = [
			dbus.String(service_name),
			dbus.ObjectPath(menuObjectPath),
			dbus.ObjectPath(actionObjectPath),
		]
		print('Fildem Lomiri app menu registered:', int(pid), service_name, menuObjectPath, actionObjectPath, flush=True)

	@dbus.service.method(LOMIRI_BUS_NAME, in_signature='uo')
	def UnregisterAppMenu(self, pid, menuObjectPath):
		pid = int(pid)
		if pid in self.app_dict and self.app_dict[pid][1] == menuObjectPath:
			del self.app_dict[pid]
		print('Fildem Lomiri app menu unregistered:', pid, menuObjectPath, flush=True)

	@dbus.service.method(LOMIRI_BUS_NAME, in_signature='soos', sender_keyword='sender')
	def RegisterSurfaceMenu(self, surface, menuObjectPath, actionObjectPath, service, sender):
		self.prune_dead_owners()
		service_name = service or sender
		self.surface_dict[str(surface)] = [
			dbus.String(service_name),
			dbus.ObjectPath(menuObjectPath),
			dbus.ObjectPath(actionObjectPath),
		]
		print('Fildem Lomiri surface menu registered:', surface, service_name, menuObjectPath, actionObjectPath, flush=True)

	@dbus.service.method(LOMIRI_BUS_NAME, in_signature='so')
	def UnregisterSurfaceMenu(self, surfaceId, menuObjectPath):
		surfaceId = str(surfaceId)
		if surfaceId in self.surface_dict and self.surface_dict[surfaceId][1] == menuObjectPath:
			del self.surface_dict[surfaceId]
		print('Fildem Lomiri surface menu unregistered:', surfaceId, menuObjectPath, flush=True)

	@dbus.service.method(LOMIRI_BUS_NAME, out_signature='a{u(soo)}')
	def GetAppMenus(self):
		self.prune_dead_owners()
		return self.app_dict

	@dbus.service.method(LOMIRI_BUS_NAME, out_signature='a{s(soo)}')
	def GetSurfaceMenus(self):
		self.prune_dead_owners()
		return self.surface_dict


class MyService(dbus.service.Object):

	BUS_PATH = '/es/inled/fildem'
	BUS_NAME = 'es.inled.fildem'

	def __init__(self):
		self.bus_name = dbus.service.BusName(self.BUS_NAME, bus=dbus.SessionBus())
		self.current_menu_tree = '[]'
		dbus.service.Object.__init__(self, self.bus_name, self.BUS_PATH)

	@dbus.service.signal(BUS_NAME, signature='su')
	def MenuActivated(self, menu, x):
		pass

	@dbus.service.method(BUS_NAME, in_signature='su')
	def EchoSignal(self, menu, x):
		self.MenuActivated(menu, x)

	@dbus.service.method(BUS_NAME, in_signature='a{ss}')
	def WindowSwitched(self, window_data):
		print('Fildem window metadata:', dict(window_data), flush=True)
		self.WindowSwitchedSignal(window_data)

	@dbus.service.signal(BUS_NAME, signature='a{ss}')
	def WindowSwitchedSignal(self, window_data):
		pass

	@dbus.service.method(BUS_NAME, in_signature='as')
	def EchoSendTopLevelMenus(self, top_level_menus):
		self.SendTopLevelMenus(top_level_menus)

	@dbus.service.signal(BUS_NAME, signature='as')
	def SendTopLevelMenus(self, top_level_menus):
		pass

	@dbus.service.method(BUS_NAME, in_signature='s')
	def EchoSendMenuTree(self, menu_tree):
		self.current_menu_tree = str(menu_tree)
		self.SendMenuTree(menu_tree)

	@dbus.service.signal(BUS_NAME, signature='s')
	def SendMenuTree(self, menu_tree):
		pass

	@dbus.service.method(BUS_NAME, in_signature='s')
	def EchoStoreMenuTree(self, menu_tree):
		self.current_menu_tree = str(menu_tree)

	@dbus.service.method(BUS_NAME, out_signature='s')
	def GetMenuTree(self):
		return self.current_menu_tree

	@dbus.service.method(BUS_NAME)
	def ClearMenuCache(self):
		self.current_menu_tree = '[]'
		self.ClearMenuCacheSignal()

	@dbus.service.signal(BUS_NAME)
	def ClearMenuCacheSignal(self):
		pass

	@dbus.service.method(BUS_NAME, in_signature='b')
	def EchoMenuOnOff(self, on):
		self.MenuOnOff(on)

	@dbus.service.signal(BUS_NAME, signature='b')
	def MenuOnOff(self, on):
		pass

	# Window action stuff (the menu on alt-space)
	@dbus.service.method(BUS_NAME)
	def RequestWindowActions(self):
		self.RequestWindowActionsSignal()

	@dbus.service.signal(BUS_NAME)
	def RequestWindowActionsSignal(self):
		pass

	@dbus.service.method(BUS_NAME, in_signature='as')
	def ListWindowActions(self, action_list):
		self.ListWindowActionsSignal(action_list)

	@dbus.service.signal(BUS_NAME, signature='as')
	def ListWindowActionsSignal(self, top_level_menus):
		pass

	@dbus.service.method(BUS_NAME, in_signature='s')
	def ActivateWindowAction(self, action):
		self.ActivateWindowActionSignal(action)

	@dbus.service.signal(BUS_NAME, signature='s')
	def ActivateWindowActionSignal(self, action):
		pass

	# Needed to activate the hud on wayland
	@dbus.service.method(BUS_NAME)
	def EmitHudActivated(self):
		self.HudActivated()

	@dbus.service.signal(BUS_NAME)
	def HudActivated(self):
		pass
