export type GatewayErrorCode = 'NETWORK' | 'TIMEOUT' | 'VALIDATION' | 'WS' | 'HTTP' | 'UNKNOWN';

export class GatewayError extends Error {
  code: GatewayErrorCode;
  detail?: unknown;

  constructor(code: GatewayErrorCode, message: string, detail?: unknown) {
    super(message);
    this.name = 'GatewayError';
    this.code = code;
    this.detail = detail;
  }
}

export function toGatewayError(error: unknown, fallback = '网关请求失败'): GatewayError {
  if (error instanceof GatewayError) return error;
  if (error instanceof DOMException && error.name === 'AbortError') {
    return new GatewayError('TIMEOUT', fallback);
  }
  if (error instanceof Error) {
    return new GatewayError('UNKNOWN', error.message || fallback, error);
  }
  return new GatewayError('UNKNOWN', fallback, error);
}
