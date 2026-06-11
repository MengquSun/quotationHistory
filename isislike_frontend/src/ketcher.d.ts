declare module "ketcher-standalone" {
  export class StandaloneStructServiceProvider {
    mode: string;
    createStructService(): unknown;
  }
}

interface Window {
  ketcher?: unknown;
}
