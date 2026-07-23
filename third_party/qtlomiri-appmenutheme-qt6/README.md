## QtLomiri-AppMenuTheme

QtLomiri-AppMenuTheme is a `QPlatformTheme` plugin which adds support for so-called "global menu" feature to Qt applications when running under Lomiri operating environment.

Support for global menu in Lomiri (formerly Unity 8) doesn't use the `com.canonical.AppMenu.Registrar` and `com.canonical.dbusmenu` interfaces. Instead, it uses an interface called `com.lomiri.MenuRegistrar` (formerly `com.ubuntu.MenuRegistrar`) for menu registration, and GMenuModel's DBus protocol from libgio to represent the menu itself.

A conversation with one of the original authors of the code reveals that `com.ubuntu.MenuRegistrar` is intended to replace `com.canonical.AppMenu.Registrar` due to the latter being built around X. It is also intended to support a menu which is associated with an application instead of a specific window in an application. However, as time passed, Unity8/Lomiri becomes the only operating environment which support this protocol. As such, this protocol is renamed to `com.lomiri.MenuRegistrar` to make it clear it is no longer associated with Ubuntu.

There is currently no plan to add support for `com.canonical.AppMenu.Registrar` protocol to Lomiri due to limited capacity on our part. On the other hand, support for `com.canonical.AppMenu.Registrar` in applications is part of Qt since 5.7.

This code was part of [QtUbuntu], the QPA plugin for MirClient protocol. It is later splitted out to also support applications using Wayland protocol.

[QtUbuntu]: https://gitlab.com/ubports/development/core/qtubuntu
