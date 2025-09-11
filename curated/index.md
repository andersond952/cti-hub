---
layout: default
title: Curated
---

<link rel="stylesheet" href="{{ '/assets/css/cards.css' | relative_url }}"/>

# Curated

Browse curated pages (vendor watches, monthly highlights).

## Vendor Watch
<ul class="card-list">
{% for p in site.pages %}
  {% if p.url contains '/curated/vendors/' and p.name != 'index.md' %}
    <li class="card">
      <div>
        <h3><a href="{{ p.url | relative_url }}">{{ p.url | split: '/' | last | replace:'.html','' }}</a></h3>
        <div class="meta">Vendor-focused feed lens</div>
      </div>
    </li>
  {% endif %}
{% endfor %}
</ul>

## Monthly/Quarterly Highlights
<ul class="card-list">
{% assign pages_sorted = site.pages | sort: 'url' | reverse %}
{% for p in pages_sorted %}
  {% if p.url contains '/curated/' and p.name != 'index.md' %}
    {% unless p.url contains '/curated/vendors/' %}
      <li class="card">
        <div>
          <h3><a href="{{ p.url | relative_url }}">{{ p.url | split: '/' | last | replace:'.html','' }}</a></h3>
          <div class="meta">Analyst summaries</div>
        </div>
      </li>
    {% endunless %}
  {% endif %}
{% endfor %}
</ul>
