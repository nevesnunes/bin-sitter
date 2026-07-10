
/// <reference types="tree-sitter-cli/dsl" />
// @ts-check

export default grammar({
	name: "ptrs",

	externals: ($) => [
		$.footer,
$.header_field1,
$.header_field2,
$.header_field3_u8x4__u8,
$.ref_header_field2__ptr16,
$.ref_header_field2__ref_header_field2_ptr__u16,
$.ref_header_field2__u16,
$.pad,
		$._pad0,
		$._err
	],

	rules: {
		Ptrs: $ => repeat(seq(
			optional($._pad0),
			choice(
				$.footer,
$.header_field1,
$.header_field2,
$.header_field3_u8x4__u8,
$.ref_header_field2__ptr16,
$.ref_header_field2__ref_header_field2_ptr__u16,
$.ref_header_field2__u16,
$.pad,
			),
		))
	}
});
