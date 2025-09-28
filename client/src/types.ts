export interface User {
  id: string;
  email: string;
  plan: string;
}

export interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
}

export interface ChatResponse {
  success: boolean;
  response: string;
  usage?: {
    input_tokens: number;
    output_tokens: number;
  };
  model?: string;
  conversation_id?: string;
}

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'error' | 'success';