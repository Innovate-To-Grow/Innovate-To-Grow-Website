/** A JSON response for `route.fulfill`. */
export function json(body: unknown, status = 200) {
  return {status, contentType: 'application/json', body: JSON.stringify(body)};
}
