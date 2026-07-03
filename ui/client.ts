import {LitElement, html} from 'lit';
import {customElement, state, property} from 'lit/decorators.js';
import {MessageProcessor} from '@a2ui/web_core/v0_9';
import {A2uiSurface, basicCatalog} from '@a2ui/lit/v0_9';

// Singleton MessageProcessor to handle all surfaces
const processor = new MessageProcessor([basicCatalog], (action) => {
  // Merge data models from ALL active surfaces to prevent regressions (MULTI-SURFACE = ONE DATA MODEL)
  let mergedDataModel = {};
  if (processor.model && typeof processor.model.getSurfaces === 'function') {
      const surfaces = processor.model.getSurfaces();
      for (const s of surfaces) {
          if (s.dataModel && typeof s.dataModel.get === 'function') {
              const data = s.dataModel.get('/');
              if (data) {
                  // Merge deeply or simply Object.assign since they share the same tree
                  mergedDataModel = deepMerge(mergedDataModel, data);
              }
          }
      }
  } else {
      console.warn("Could not retrieve surfaces from processor model. Fallback to current surface only.");
      const surface = processor.model?.getSurface?.(action.surfaceId);
      mergedDataModel = surface ? (surface.dataModel?.get?.('/') || {}) : {};
  }

  fetch('/api/action', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      action: action,
      dataModel: mergedDataModel
    })
  }).then(res => res.json()).then(data => {
    if (data.redirect) {
      window.location.href = data.redirect;
    }
  }).catch(e => console.error("Action error:", e));
});

// Expose processor for UI tests
(window as any).a2ui_processor = processor;

// Simple deep merge helper for Pydantic-like JSON models
function deepMerge(target: any, source: any) {
  if (typeof target !== 'object' || target === null) return source;
  if (typeof source !== 'object' || source === null) return source;
  
  for (const key of Object.keys(source)) {
    if (source[key] instanceof Object && key in target) {
      Object.assign(source[key], deepMerge(target[key], source[key]));
    }
  }
  Object.assign(target || {}, source);
  return target;
}

let fetched = false;
function ensureFetched() {
  if (fetched) return;
  fetched = true;
  fetch('/api/messages')
    .then(r => r.json())
    .then(messages => processor.processMessages(messages))
    .catch(e => console.error("Messages fetch error:", e));
}

@customElement('my-app')
export class MyApp extends LitElement {
  @property({ type: String, attribute: 'surface-id' })
  surfaceId: string = 'main';

  get processor() {
    return processor;
  }

  @state()
  private surface: any;

  connectedCallback() {
    super.connectedCallback();

    processor.onSurfaceCreated(s => {
      if (s.id === this.surfaceId) {
        this.surface = s;
      }
    });

    ensureFetched();
  }

  // We disable Shadow DOM so global CSS can penetrate if necessary, though A2UI handles its own rendering.
  createRenderRoot() {
    return this;
  }

  render() {
    return this.surface
      ? html`<a2ui-surface .surface=${this.surface}></a2ui-surface>`
      : html`<div style="color: #A0AEC0; font-size: 0.9rem;">Chargement...</div>`;
  }
}
