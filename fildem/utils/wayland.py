import glob
import os
import stat


def _has_wayland_socket():
	runtime_dir = os.environ.get('XDG_RUNTIME_DIR')
	if not runtime_dir:
		return False

	for candidate in glob.glob(os.path.join(runtime_dir, 'wayland-*')):
		if candidate.endswith('.lock'):
			continue
		try:
			mode = os.stat(candidate).st_mode
		except OSError:
			continue
		if stat.S_ISSOCK(mode):
			return True
	return False


def is_wayland():
	session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
	if session_type == 'wayland':
		return True
	if session_type == 'x11':
		return False

	disp = os.environ.get('WAYLAND_DISPLAY')
	if disp:
		return True

	return _has_wayland_socket()
