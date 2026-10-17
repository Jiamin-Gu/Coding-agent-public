'use strict';

/**
 * Convert a title/string into a URL-friendly slug:
 * - lowercase the input
 * - replace runs of spaces and punctuation with a single hyphen
 * - strip leading and trailing hyphens
 *
 * @param {*} input - the value to slugify (converted to String)
 * @returns {string} slug
 */
function slugify(input) {
  return String(input)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-') // spaces + punctuation -> hyphen
    .replace(/^-+|-+$/g, '');    // trim leading/trailing hyphens
}

module.exports = slugify;