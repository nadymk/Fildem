/*
 * Copyright (C) 2016-2017 Canonical, Ltd.
 *
 * This program is free software: you can redistribute it and/or modify it under
 * the terms of the GNU Lesser General Public License version 3, as published by
 * the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
 * SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

#include <QVariant>
#include <QtGui/qpa/qplatformthemefactory_p.h>
#if QT_VERSION < QT_VERSION_CHECK(6, 0, 0)
#include <QtThemeSupport/private/qgenericunixthemes_p.h>
#else
#include <QtGui/private/qgenericunixtheme_p.h>
#endif
#include <QGuiApplication>
#include <QIcon>
#include <QIconEngine>
#include <QPalette>
#include <QPixmap>
#include <QScreen>
#include <QStringList>

#include <memory>

class LomiriTheme : public QGenericUnixTheme
{
public:
    LomiriTheme()
      : mBaseTheme(createBaseTheme()),
        mSystemFont(QStringLiteral("Ubuntu Regular"), 10),
        mFixedFont(QStringLiteral("Ubuntu Mono Regular"), 13)
    {
        mSystemFont.setStyleHint(QFont::System);
        mFixedFont.setStyleHint(QFont::TypeWriter);
    }
    ~LomiriTheme() = default;

    QVariant themeHint(ThemeHint hint) const override
    {
        if (mBaseTheme) {
            const QVariant value = mBaseTheme->themeHint(hint);
            if (value.isValid())
                return value;
        }

        switch (hint) {
        case QPlatformTheme::SystemIconThemeName: {
            QByteArray iconTheme = qgetenv("QTUBUNTU_ICON_THEME");
            if (iconTheme.isEmpty()) {
                return QStringLiteral("suru");
            } else {
                return iconTheme;
            }
        }
        case QPlatformTheme::MouseDoubleClickDistance: {
            // Impl mostly yoinked from the QAndroidPlatformTheme
            QScreen *screen = qGuiApp->primaryScreen();
            if (screen) {
                qreal dotsPerInch = screen->physicalDotsPerInch();
                // Allow 15% of an inch between taps when double clicking
                return qRound(dotsPerInch * 0.15);
            } else {
                return 5;
            }
        }
        case QPlatformTheme::TouchDoubleTapDistance: {
            bool ok = false;
            int dist = themeHint(QPlatformTheme::MouseDoubleClickDistance).toInt(&ok) * 2;
            return QVariant(ok ? dist : 10);
        }
        default:
            break;
        }
        return QGenericUnixTheme::themeHint(hint);
    }

    const QFont *font(Font type) const override
    {
        if (mBaseTheme) {
            const QFont *baseFont = mBaseTheme->font(type);
            if (baseFont)
                return baseFont;
        }

        switch (type) {
        case QPlatformTheme::SystemFont:
            return &mSystemFont;
        case QPlatformTheme::FixedFont:
            return &mFixedFont;
        default:
            return nullptr;
        }
    }

    bool usePlatformNativeDialog(DialogType type) const override
    {
        return mBaseTheme ? mBaseTheme->usePlatformNativeDialog(type)
                          : QGenericUnixTheme::usePlatformNativeDialog(type);
    }

    QPlatformDialogHelper *createPlatformDialogHelper(DialogType type) const override
    {
        return mBaseTheme ? mBaseTheme->createPlatformDialogHelper(type)
                          : QGenericUnixTheme::createPlatformDialogHelper(type);
    }

#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    Qt::ColorScheme colorScheme() const override
    {
        return mBaseTheme ? mBaseTheme->colorScheme()
                          : QGenericUnixTheme::colorScheme();
    }
#endif

    const QPalette *palette(Palette type = SystemPalette) const override
    {
        if (mBaseTheme) {
            const QPalette *basePalette = mBaseTheme->palette(type);
            if (basePalette)
                return basePalette;
        }
        return QGenericUnixTheme::palette(type);
    }

    QPixmap standardPixmap(StandardPixmap sp, const QSizeF &size) const override
    {
        return mBaseTheme ? mBaseTheme->standardPixmap(sp, size)
                          : QGenericUnixTheme::standardPixmap(sp, size);
    }

    QIcon fileIcon(const QFileInfo &fileInfo,
                   QPlatformTheme::IconOptions iconOptions = { }) const override
    {
        return mBaseTheme ? mBaseTheme->fileIcon(fileInfo, iconOptions)
                          : QGenericUnixTheme::fileIcon(fileInfo, iconOptions);
    }

    QIconEngine *createIconEngine(const QString &iconName) const override
    {
        return mBaseTheme ? mBaseTheme->createIconEngine(iconName)
                          : QGenericUnixTheme::createIconEngine(iconName);
    }

#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
#if QT_CONFIG(shortcut)
    QList<QKeySequence> keyBindings(QKeySequence::StandardKey key) const override
    {
        return mBaseTheme ? mBaseTheme->keyBindings(key)
                          : QGenericUnixTheme::keyBindings(key);
    }
#endif
#else
#ifndef QT_NO_SHORTCUT
    QList<QKeySequence> keyBindings(QKeySequence::StandardKey key) const override
    {
        return mBaseTheme ? mBaseTheme->keyBindings(key)
                          : QGenericUnixTheme::keyBindings(key);
    }
#endif
#endif

    QString standardButtonText(int button) const override
    {
        return mBaseTheme ? mBaseTheme->standardButtonText(button)
                          : QGenericUnixTheme::standardButtonText(button);
    }

#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
#if QT_CONFIG(shortcut)
    QKeySequence standardButtonShortcut(int button) const override
    {
        return mBaseTheme ? mBaseTheme->standardButtonShortcut(button)
                          : QGenericUnixTheme::standardButtonShortcut(button);
    }
#endif
#else
    QKeySequence standardButtonShortcut(int button) const override
    {
        return mBaseTheme ? mBaseTheme->standardButtonShortcut(button)
                          : QGenericUnixTheme::standardButtonShortcut(button);
    }
#endif

#if QT_VERSION >= QT_VERSION_CHECK(6, 0, 0)
    void requestColorScheme(Qt::ColorScheme scheme) override
    {
        if (mBaseTheme)
            mBaseTheme->requestColorScheme(scheme);
        else
            QGenericUnixTheme::requestColorScheme(scheme);
    }

    Qt::ContrastPreference contrastPreference() const override
    {
        return mBaseTheme ? mBaseTheme->contrastPreference()
                          : QGenericUnixTheme::contrastPreference();
    }
#endif

protected:
    QPlatformTheme *baseTheme() const
    {
        return mBaseTheme.get();
    }

private:
    static QPlatformTheme *createBaseTheme()
    {
        QStringList candidates;

        const QByteArray forced = qgetenv("FILDEM_QT_BASE_PLATFORMTHEME");
        if (!forced.isEmpty())
            candidates << QString::fromLocal8Bit(forced);

        const QString desktop = QString::fromLocal8Bit(qgetenv("XDG_CURRENT_DESKTOP")).toLower();
        if (desktop.contains(QStringLiteral("kde")))
            candidates << QStringLiteral("kde");
        if (desktop.contains(QStringLiteral("gnome")) || desktop.contains(QStringLiteral("ubuntu")))
            candidates << QStringLiteral("gtk3") << QStringLiteral("gnome") << QStringLiteral("xdgdesktopportal");

        candidates << QStringLiteral("gtk3") << QStringLiteral("lxqt") << QStringLiteral("gnome")
                   << QStringLiteral("kde") << QStringLiteral("xdgdesktopportal");
        candidates.removeAll(QStringLiteral("lomiriappmenu"));
        candidates.removeDuplicates();

        const QStringList pluginKeys = QPlatformThemeFactory::keys();
        for (const QString &candidate : candidates) {
            QPlatformTheme *theme = nullptr;
            if (pluginKeys.contains(candidate, Qt::CaseInsensitive))
                theme = QPlatformThemeFactory::create(candidate);
            if (!theme)
                theme = QGenericUnixTheme::createUnixTheme(candidate);
            if (theme)
                return theme;
        }

        return nullptr;
    }

    std::unique_ptr<QPlatformTheme> mBaseTheme;
    QFont mSystemFont, mFixedFont;
};
