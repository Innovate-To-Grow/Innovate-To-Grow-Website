// Strongly connected components of an import graph (Tarjan), for check-structure.mjs's cycle check.

export function stronglyConnected(graph) {
  let counter = 0
  const index = new Map()
  const low = new Map()
  const stack = []
  const onStack = new Set()
  const components = []
  const connect = (node) => {
    index.set(node, counter)
    low.set(node, counter)
    counter += 1
    stack.push(node)
    onStack.add(node)
    for (const next of graph.get(node) ?? []) {
      if (!index.has(next)) {
        connect(next)
        low.set(node, Math.min(low.get(node), low.get(next)))
      } else if (onStack.has(next)) {
        low.set(node, Math.min(low.get(node), index.get(next)))
      }
    }
    if (low.get(node) === index.get(node)) {
      const component = []
      let member
      do {
        member = stack.pop()
        onStack.delete(member)
        component.push(member)
      } while (member !== node)
      if (component.length > 1) components.push(component.sort())
    }
  }
  for (const node of [...graph.keys()].sort()) if (!index.has(node)) connect(node)
  return components
}
