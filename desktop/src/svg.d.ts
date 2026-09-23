// Vite serves imported .svg files as a URL string.
declare module "*.svg" {
  const src: string;
  export default src;
}

// `?raw` gives the file's text content (used to inline the animated brand SVG).
declare module "*.svg?raw" {
  const content: string;
  export default content;
}
