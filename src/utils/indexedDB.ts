import { Note } from '../types';

const DB_NAME = 'WorkspaceNotesDB';
const DB_VERSION = 1;
const STORE_NAME = 'notes';

/**
 * Open the IndexedDB database and handle creation/upgrades.
 */
export function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof window === 'undefined' || !window.indexedDB) {
      reject(new Error('IndexedDB is not supported in this environment.'));
      return;
    }

    const request = window.indexedDB.open(DB_NAME, DB_VERSION);

    request.onerror = () => {
      reject(request.error || new Error('Failed to open database.'));
    };

    request.onsuccess = () => {
      resolve(request.result);
    };

    request.onupgradeneeded = (event) => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        // Index to quickly query all notes for a specific topic
        store.createIndex('topic_id', 'topic_id', { unique: false });
        // Composite-like query support: index by topic_id and depth
        store.createIndex('topic_depth', ['topic_id', 'depth'], { unique: false });
      }
    };
  });
}

/**
 * Save a single note to the IndexedDB cache.
 */
export async function saveNoteToCache(note: Note): Promise<void> {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.put(note);

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error || new Error('Failed to save note.'));
    });
  } catch (error) {
    console.error('Error saving note to IndexedDB:', error);
  }
}

/**
 * Save multiple notes to the IndexedDB cache.
 */
export async function saveNotesToCache(notes: Note[]): Promise<void> {
  if (!notes || notes.length === 0) return;
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, 'readwrite');
      const store = transaction.objectStore(STORE_NAME);

      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error || new Error('Failed to save notes transaction.'));

      for (const note of notes) {
        store.put(note);
      }
    });
  } catch (error) {
    console.error('Error bulk saving notes to IndexedDB:', error);
  }
}

/**
 * Get a note from cache matching topic_id and depth.
 */
export async function getNoteFromCache(topicId: string, depth: string): Promise<Note | null> {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      
      // Use the topic_depth index to find exact matches
      const index = store.index('topic_depth');
      const request = index.get([topicId, depth]);

      request.onsuccess = () => {
        resolve(request.result || null);
      };

      request.onerror = () => {
        reject(request.error || new Error('Failed to fetch note from cache.'));
      };
    });
  } catch (error) {
    console.error('Error reading note from IndexedDB:', error);
    return null;
  }
}

/**
 * Get all notes cached for a specific topic.
 */
export async function getNotesForTopicFromCache(topicId: string): Promise<Note[]> {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const index = store.index('topic_id');
      const request = index.getAll(topicId);

      request.onsuccess = () => {
        resolve(request.result || []);
      };

      request.onerror = () => {
        reject(request.error || new Error('Failed to fetch topic notes from cache.'));
      };
    });
  } catch (error) {
    console.error('Error reading topic notes from IndexedDB:', error);
    return [];
  }
}

/**
 * Get a map of topic_ids that have at least one note cached.
 */
export async function getCachedTopicIdsMap(): Promise<Record<string, boolean>> {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, 'readonly');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.getAll();

      request.onsuccess = () => {
        const results = request.result || [];
        const map: Record<string, boolean> = {};
        for (const item of results) {
          if (item.topic_id) {
            map[item.topic_id] = true;
          }
        }
        resolve(map);
      };

      request.onerror = () => {
        reject(request.error || new Error('Failed to load notes for cached topics map.'));
      };
    });
  } catch (error) {
    console.error('Error fetching cached topic IDs map:', error);
    return {};
  }
}

/**
 * Clear cache (e.g. for user storage cleanup).
 */
export async function clearNoteCache(): Promise<void> {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(STORE_NAME, 'readwrite');
      const store = transaction.objectStore(STORE_NAME);
      const request = store.clear();

      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error || new Error('Failed to clear note cache.'));
    });
  } catch (error) {
    console.error('Error clearing IndexedDB notes store:', error);
  }
}
