import { Subject } from '../types';

export interface ClassroomCourse {
  id: string;
  name: string;
  section?: string;
  descriptionHeading?: string;
}

export interface ClassroomMaterial {
  id: string;
  title: string;
  type: 'material' | 'coursework';
  mimeType?: string;
  alternateLink?: string;
  source: string;
  description?: string;
}

export interface ClassroomMapping {
  id: string;
  course_id: string;
  course_name: string;
  subject_id: string;
  folder_id?: string;
  folder_name?: string;
}

export interface ClassroomFolder {
  id: string;
  name: string;
  mimeType: string;
}

export class ClassroomIntegrationService {
  private accessToken: string | null;

  constructor(accessToken: string | null) {
    this.accessToken = accessToken;
  }

  /**
   * Update the authorization token used for API requests.
   */
  setAccessToken(token: string | null) {
    this.accessToken = token;
  }

  /**
   * Fetches Google Classroom courses linked to the user's account.
   */
  async fetchCourses(): Promise<ClassroomCourse[]> {
    if (!this.accessToken) {
      throw new Error('OAuth Access Token is required to fetch Classroom courses.');
    }
    const response = await fetch(`/api/classroom/courses?accessToken=${this.accessToken}`);
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(errText || 'Failed to fetch Classroom courses');
    }
    return response.json();
  }

  /**
   * Fetches materials and coursework assignments for a Google Classroom course.
   */
  async fetchCourseMaterials(courseId: string): Promise<ClassroomMaterial[]> {
    if (!this.accessToken) {
      throw new Error('OAuth Access Token is required to fetch classroom materials.');
    }
    const response = await fetch(`/api/classroom/courses/${courseId}/materials?accessToken=${this.accessToken}`);
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(errText || 'Failed to fetch course materials');
    }
    return response.json();
  }

  /**
   * Fetches nested folders from the course's Drive folder hierarchy.
   */
  async fetchCourseFolders(courseId: string): Promise<ClassroomFolder[]> {
    if (!this.accessToken) {
      throw new Error('OAuth Access Token is required to fetch course folders.');
    }
    const response = await fetch(`/api/classroom/courses/${courseId}/folders?accessToken=${this.accessToken}`);
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(errText || 'Failed to fetch course folders');
    }
    return response.json();
  }

  /**
   * Lists supported reference files (PDFs/Docs) from a mapped Classroom/Drive folder.
   */
  async fetchMappedFiles(mappingId: string): Promise<any[]> {
    if (!this.accessToken) {
      throw new Error('OAuth Access Token is required to fetch mapped files.');
    }
    const response = await fetch(`/api/classroom/mappings/${mappingId}/files?accessToken=${this.accessToken}`);
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(errText || 'Failed to fetch mapped files');
    }
    return response.json();
  }

  /**
   * Fetches all current Classroom-to-Subject mappings from the Tattva DB.
   */
  static async fetchMappings(): Promise<ClassroomMapping[]> {
    const response = await fetch('/api/classroom/mappings');
    if (!response.ok) {
      throw new Error('Failed to retrieve academic mappings.');
    }
    return response.json();
  }

  /**
   * Connects/Maps a Google Classroom course/folder combination to a local academic subject.
   */
  static async createMapping(mapping: Omit<ClassroomMapping, 'id'>): Promise<ClassroomMapping> {
    const response = await fetch('/api/classroom/mappings', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(mapping),
    });
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(errText || 'Failed to link Google Classroom course to subject.');
    }
    return response.json();
  }

  /**
   * Deletes a Classroom-to-Subject connection mapping.
   */
  static async deleteMapping(id: string): Promise<void> {
    const response = await fetch(`/api/classroom/mappings/${id}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      const errText = await response.text();
      throw new Error(errText || 'Failed to sever connection mapping.');
    }
  }
}
