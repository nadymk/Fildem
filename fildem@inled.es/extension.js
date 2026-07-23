import { Extension } from 'resource:///org/gnome/shell/extensions/extension.js';
import { NativeMenuManager } from './nativeMenuManager.js';

export default class FildemExtension extends Extension {
    enable() {
        this._menuManager = new NativeMenuManager();
    }

    disable() {
        this._menuManager?.destroy();
        this._menuManager = null;
    }
}
