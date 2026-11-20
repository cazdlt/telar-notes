import type { Extension } from '@codemirror/state';
import type { TasksSettings, PeriodicNotesSettings, FolderNotesSettings, VaultPluginSettings } from './types';

export type PluginSettingsField = { key: string; label: string; type: 'boolean' | 'text' | 'select'; options?: { value: string; label: string }[] };
export type PluginContext = { addRibbonAction: (id: string, action: () => void) => void; addCodeMirrorExtension: (extension: Extension) => void; readSettings: () => VaultPluginSettings; writeSettings: (settings: VaultPluginSettings) => Promise<void> };
export type PluginDefinition<TSettings> = { id: keyof VaultPluginSettings['plugins']; name: string; defaults: TSettings; enabled: (settings: TSettings) => boolean; fields: PluginSettingsField[]; activate?: (context: PluginContext) => void | (() => void) };

const plugins = new Map<string, PluginDefinition<unknown>>();

export function registerPlugin<TSettings>(plugin: PluginDefinition<TSettings>): PluginDefinition<TSettings> {
  plugins.set(plugin.id, plugin as PluginDefinition<unknown>);
  return plugin;
}

export function registeredPlugins(): PluginDefinition<unknown>[] { return [...plugins.values()]; }

export const tasksPlugin = registerPlugin<TasksSettings>({
  id: 'tasks', name: 'Tasks', defaults: { enabled: true, next_status_symbol: 'x', set_done_date: true, set_cancelled_date: true, set_created_date: true }, enabled: (settings) => settings.enabled,
  fields: [{ key: 'enabled', label: 'Enabled', type: 'boolean' }, { key: 'next_status_symbol', label: 'Next status', type: 'select', options: [{ value: 'x', label: 'Done' }, { value: '/', label: 'In progress' }, { value: '-', label: 'Cancelled' }] }, { key: 'set_done_date', label: 'Set done date', type: 'boolean' }, { key: 'set_cancelled_date', label: 'Set cancelled date', type: 'boolean' }, { key: 'set_created_date', label: 'Set created date', type: 'boolean' }],
});

export const periodicNotesPlugin = registerPlugin<PeriodicNotesSettings>({
  id: 'periodic-notes', name: 'Periodic Notes', defaults: { enabled: true, folder: 'diario', format: 'YYYY/MM/YYYY-MM-DD', template: 'templates/daily.md' }, enabled: (settings) => settings.enabled,
  fields: [{ key: 'enabled', label: 'Enabled', type: 'boolean' }, { key: 'folder', label: 'Daily folder', type: 'text' }, { key: 'format', label: 'Daily format', type: 'text' }, { key: 'template', label: 'Daily template', type: 'text' }],
});

export const folderNotesPlugin = registerPlugin<FolderNotesSettings>({
  id: 'folder-notes', name: 'Folder Notes', defaults: { enabled: false }, enabled: (settings) => settings.enabled,
  fields: [{ key: 'enabled', label: 'Enabled', type: 'boolean' }],
});
