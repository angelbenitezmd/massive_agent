import contractJson from "../../shared/api-contract.json";

type ContractRoute = {
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
};

type ApiContract = {
  version: string;
  routes: Record<string, ContractRoute>;
};

export const API_CONTRACT: ApiContract = contractJson as ApiContract;

export function contractPath(
  key: keyof typeof API_CONTRACT.routes | string,
  params?: Record<string, string | number>
): string {
  const route = API_CONTRACT.routes[key];
  if (!route) {
    throw new Error(`Unknown contract route: ${String(key)}`);
  }
  let path = route.path;
  for (const [param, value] of Object.entries(params || {})) {
    path = path.replace(`:${param}`, encodeURIComponent(String(value)));
  }
  return path;
}

