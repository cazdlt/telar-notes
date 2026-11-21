import { describe, expect, it } from 'vitest';
import {
  folderNotesPlugin,
  periodicNotesPlugin,
  registeredPlugins,
  registerPlugin,
  tasksPlugin,
} from './plugins';

describe('built-in plugins', () => {
  it('registers tasks, periodic-notes, and folder-notes with expected defaults and enabled checks', () => {
    const ids = registeredPlugins().map((plugin) => plugin.id);
    expect(ids).toEqual(['tasks', 'periodic-notes', 'folder-notes']);

    expect(tasksPlugin.defaults.enabled).toBe(true);
    expect(tasksPlugin.enabled({ ...tasksPlugin.defaults, enabled: false })).toBe(false);

    expect(periodicNotesPlugin.defaults).toEqual({
      enabled: true,
      folder: 'diario',
      format: 'YYYY/MM/YYYY-MM-DD',
      template: 'templates/daily.md',
    });
    expect(periodicNotesPlugin.enabled(periodicNotesPlugin.defaults)).toBe(true);

    expect(folderNotesPlugin.defaults.enabled).toBe(true);
    expect(folderNotesPlugin.enabled(folderNotesPlugin.defaults)).toBe(true);
    expect(folderNotesPlugin.enabled({ ...folderNotesPlugin.defaults, enabled: false })).toBe(false);
  });

  it('defines settings fields matching each plugin defaults keys', () => {
    for (const plugin of [tasksPlugin, periodicNotesPlugin, folderNotesPlugin]) {
      const defaultKeys = Object.keys(plugin.defaults);
      expect(plugin.fields.map((field) => field.key)).toEqual(defaultKeys);
    }

    const nextStatus = tasksPlugin.fields.find((field) => field.key === 'next_status_symbol');
    expect(nextStatus?.type).toBe('select');
    expect(nextStatus?.options?.map((option) => option.value)).toEqual(['x', '/', '-']);
  });
});

describe('registerPlugin', () => {
  it('replaces an existing plugin with the same id without creating duplicates', () => {
    const replacement = { ...folderNotesPlugin, name: 'Folder Notes Custom' };
    try {
      expect(registerPlugin(replacement)).toBe(replacement);
      const matches = registeredPlugins().filter((plugin) => plugin.id === 'folder-notes');
      expect(matches).toHaveLength(1);
      expect(matches[0].name).toBe('Folder Notes Custom');
    } finally {
      registerPlugin(folderNotesPlugin);
    }
  });
});
