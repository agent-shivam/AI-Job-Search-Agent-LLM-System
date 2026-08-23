"""
pdf_generator.py
----------------
Generates a styled, professional PDF from a tailored resume JSON object using ReportLab.
"""

import os
import logging
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

logger = logging.getLogger(__name__)

def generate_resume_pdf(resume_data: dict, output_path: str) -> str:
    """
    Takes a resume dictionary and compiles it to a PDF at output_path.
    Returns the output path of the generated PDF.
    """
    # Ensure target directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    
    # Page setup
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )
    
    story = []
    styles = getSampleStyleSheet()
    
    # ── Custom Styles ──────────────────────────────────────────────────────────
    # Primary brand colors (sleek dark palette)
    primary_color = colors.HexColor('#1a1a2e')  # Dark slate
    secondary_color = colors.HexColor('#16213e') # Deep blue
    accent_color = colors.HexColor('#0f3460')    # Vibrant dark blue
    text_color = colors.HexColor('#333333')      # Clean charcoal
    light_line_color = colors.HexColor('#dddddd')# Light grey for borders
    
    title_style = ParagraphStyle(
        'ResumeName',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=primary_color,
        spaceAfter=3
    )
    
    subtitle_style = ParagraphStyle(
        'ResumeTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=accent_color,
        spaceAfter=6
    )
    
    contact_style = ParagraphStyle(
        'ResumeContact',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=text_color,
        spaceAfter=8
    )
    
    section_heading_style = ParagraphStyle(
        'ResumeSectionHeader',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=14,
        textColor=primary_color,
        spaceBefore=12,
        spaceAfter=4,
        keepWithNext=True
    )
    
    body_style = ParagraphStyle(
        'ResumeBodyText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13,
        textColor=text_color,
        spaceAfter=4
    )
    
    bullet_style = ParagraphStyle(
        'ResumeBullet',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=12.5,
        textColor=text_color,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=2
    )

    # ── Helper to add Section Dividers ─────────────────────────────────────────
    def add_section_divider(title: str):
        story.append(Paragraph(title, section_heading_style))
        line_table = Table([['']], colWidths=[532], rowHeights=[1.5])
        line_table.setStyle(TableStyle([
            ('LINEBELOW', (0,0), (-1,-1), 1.5, primary_color),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(line_table)
        story.append(Spacer(1, 6))

    # ── 1. Header (Name, Title, Contact) ───────────────────────────────────────
    name = resume_data.get('name', 'Candidate Name')
    title = resume_data.get('title', '')
    story.append(Paragraph(name, title_style))
    if title:
        story.append(Paragraph(title, subtitle_style))
        
    # Format contact items
    contact = resume_data.get('contact', {})
    contact_parts = []
    if contact.get('email'):
        contact_parts.append(f"📧 {contact['email']}")
    if contact.get('phone'):
        contact_parts.append(f"📞 {contact['phone']}")
    if contact.get('location'):
        contact_parts.append(f"📍 {contact['location']}")
    if contact.get('linkedin'):
        contact_parts.append(f"🔗 {contact['linkedin']}")
    if contact.get('github'):
        contact_parts.append(f"💻 {contact['github']}")
        
    contact_text = "  |  ".join(contact_parts)
    story.append(Paragraph(contact_text, contact_style))
    
    # ── 2. Summary ─────────────────────────────────────────────────────────────
    summary = resume_data.get('summary', '')
    if summary:
        add_section_divider("PROFESSIONAL SUMMARY")
        story.append(Paragraph(summary, body_style))
        story.append(Spacer(1, 4))
        
    # ── 3. Technical Skills ────────────────────────────────────────────────────
    skills = resume_data.get('skills', {})
    if skills:
        add_section_divider("TECHNICAL SKILLS")
        
        # Determine format (skills can be a list or dictionary of lists)
        if isinstance(skills, dict):
            for category, skill_list in skills.items():
                if skill_list:
                    cat_name = category.replace('_', ' ').title()
                    # Clean up category names
                    if cat_name == "Ml Ai":
                        cat_name = "Machine Learning & AI"
                    elif cat_name == "Llm Systems":
                        cat_name = "LLM & Agent Systems"
                    elif cat_name == "Vector Dbs":
                        cat_name = "Vector Databases"
                    
                    skills_str = ", ".join(skill_list)
                    story.append(Paragraph(f"<b>{cat_name}:</b> {skills_str}", body_style))
        elif isinstance(skills, list) and skills:
            story.append(Paragraph(", ".join(skills), body_style))
            
        story.append(Spacer(1, 4))
        
    # ── 4. Projects ────────────────────────────────────────────────────────────
    projects = resume_data.get('projects', [])
    if projects:
        add_section_divider("KEY PROJECTS")
        for proj in projects:
            proj_name = proj.get('name', '')
            tech = proj.get('tech', [])
            bullets = proj.get('bullets', [])
            
            proj_header = f"<b>{proj_name}</b>"
            if tech:
                proj_header += f" — <i>{', '.join(tech)}</i>"
                
            story.append(Paragraph(proj_header, body_style))
            for bullet in bullets:
                story.append(Paragraph(f"&bull;&nbsp;&nbsp;{bullet}", bullet_style))
            story.append(Spacer(1, 4))
            
    # ── 5. Education ───────────────────────────────────────────────────────────
    education = resume_data.get('education', [])
    if education:
        add_section_divider("EDUCATION")
        for edu in education:
            degree = edu.get('degree', '')
            institution = edu.get('institution', '')
            grad = edu.get('graduation', '')
            loc = edu.get('location', '')
            coursework = edu.get('coursework', [])
            
            edu_line = f"<b>{degree}</b> | {institution}"
            if loc:
                edu_line += f", {loc}"
            if grad:
                edu_line += f" ({grad})"
                
            story.append(Paragraph(edu_line, body_style))
            if coursework:
                cw_str = ", ".join(coursework)
                story.append(Paragraph(f"<i>Relevant Coursework:</i> {cw_str}", bullet_style))
            story.append(Spacer(1, 3))
            
    # ── 6. Strengths ───────────────────────────────────────────────────────────
    strengths = resume_data.get('strengths', [])
    if strengths:
        add_section_divider("STRENGTHS & COMPETENCIES")
        for strength in strengths:
            story.append(Paragraph(f"&bull;&nbsp;&nbsp;{strength}", bullet_style))
            
    # Compile the doc
    try:
        doc.build(story)
        logger.info(f"Successfully generated PDF resume at {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Failed to generate PDF: {e}")
        raise e
