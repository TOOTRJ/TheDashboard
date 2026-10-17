export class ApiInputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ApiInputError";
  }
}

export class ApiConfigurationError extends Error {
  constructor() {
    super("API service is unavailable");
    this.name = "ApiConfigurationError";
  }
}

export function logApiFailure(code: "CONFIGURATION" | "DATABASE_READ" | "DATABASE_WRITE" | "UNEXPECTED") {
  console.error("Dashboard API failure", code);
}
