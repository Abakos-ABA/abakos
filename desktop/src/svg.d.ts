// Vite serves imported .svg files as a URL string.
declare module "*.svg" {
  const src: string;
  export default src;
}
