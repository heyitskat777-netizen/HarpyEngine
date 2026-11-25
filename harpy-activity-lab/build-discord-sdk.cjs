const path = require("node:path");
const esbuild = require("esbuild");

const runtime = process.env.HARPY_ACTIVITY_RUNTIME_ROOT
  ? path.resolve(process.env.HARPY_ACTIVITY_RUNTIME_ROOT, "discord-sdk")
  : path.resolve(__dirname, "../.sites-runtime/harpyengine-mission-lab/discord-sdk");
esbuild.buildSync({
  stdin: {
    contents: 'export { DiscordSDK } from "@discord/embedded-app-sdk";',
    resolveDir: __dirname,
  },
  bundle: true,
  platform: "browser",
  format: "esm",
  minify: true,
  outfile: path.join(runtime, "embedded-app.js"),
});
