import postcssRTLCSS from "postcss-rtlcss";

export default {
  plugins: [
    (await import("tailwindcss")).default,
    (await import("autoprefixer")).default,
    // Arabic: adds [dir="rtl"] overrides for what is physical (ml-2, left-0...); left-to-right
    // pages keep exactly the rules they had
    postcssRTLCSS({ mode: "override" }),
  ],
};
