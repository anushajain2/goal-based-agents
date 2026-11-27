"""Launch videos made from a company's own website.

  capture.py     a headless browser visits the site: screenshots, brand colours, fonts, logo and copy
  storyboard.py  Claude looks at them and writes the video as data (scenes, words, focus areas)
  render.py      fixed Remotion templates (../../video) turn the storyboard into launch.mp4 + poster.jpg

Nothing written by the model is ever run as code: the storyboard is data for our own templates.
"""
