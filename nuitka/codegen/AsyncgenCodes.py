#     Copyright 2018, Kay Hayen, mailto:kay.hayen@gmail.com
#
#     Part of "Nuitka", an optimizing Python compiler that is compatible and
#     integrates with CPython, but also works on its own.
#
#     Licensed under the Apache License, Version 2.0 (the "License");
#     you may not use this file except in compliance with the License.
#     You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#     Unless required by applicable law or agreed to in writing, software
#     distributed under the License is distributed on an "AS IS" BASIS,
#     WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#     See the License for the specific language governing permissions and
#     limitations under the License.
#
""" Code to generate and interact with compiled asyncgen objects.

"""

from .CodeHelpers import generateStatementSequenceCode
from .Emission import SourceCodeCollector
from .FunctionCodes import (
    finalizeFunctionLocalVariables,
    getClosureCopyCode,
    getFunctionQualnameObj,
    setupFunctionLocalVariables
)
from .Indentation import indented
from .ModuleCodes import getModuleAccessCode
from .templates.CodeTemplatesAsyncgens import (
    template_asyncgen_exception_exit,
    template_asyncgen_noexception_exit,
    template_asyncgen_object_body_template,
    template_asyncgen_object_maker_template,
    template_asyncgen_return_exit,
    template_make_asyncgen
)
from .YieldCodes import getYieldReturnDispatchCode


def getAsyncgenObjectDeclCode(function_identifier):
    return template_asyncgen_object_maker_template % {
        "function_identifier" : function_identifier,
    }


def getAsyncgenObjectCode(context, function_identifier, closure_variables,
                          user_variables, outline_variables,
                          temp_variables, needs_exception_exit,
                          needs_generator_return):
    # A bit of details going on here, pylint: disable=too-many-locals

    setupFunctionLocalVariables(
        context           = context,
        parameters        = None,
        closure_variables = closure_variables,
        user_variables    = user_variables + outline_variables,
        temp_variables    = temp_variables
    )

    function_codes = SourceCodeCollector()

    asyncgen_object_body = context.getOwner()

    generateStatementSequenceCode(
        statement_sequence = asyncgen_object_body.getBody(),
        allow_none         = True,
        emit               = function_codes,
        context            = context
    )

    function_cleanup = finalizeFunctionLocalVariables(context)

    if needs_exception_exit:
        exception_type, exception_value, exception_tb, _exception_lineno = \
          context.variable_storage.getExceptionVariableDescriptions()

        generator_exit = template_asyncgen_exception_exit % {
            "function_identifier" : function_identifier,
            "function_cleanup"    : indented(function_cleanup),
            "exception_type"      : exception_type,
            "exception_value"     : exception_value,
            "exception_tb"        : exception_tb
        }
    else:
        generator_exit = template_asyncgen_noexception_exit % {
            "function_identifier" : function_identifier,
            "function_cleanup"    : indented(function_cleanup)
        }

    if needs_generator_return:
        generator_exit += template_asyncgen_return_exit % {}

    function_locals = context.variable_storage.makeCFunctionLevelDeclarations()

    local_type_decl = context.variable_storage.makeCStructLevelDeclarations()
    function_locals += context.variable_storage.makeCStructInits()

    if local_type_decl:
        heap_declaration = """\
struct %(function_identifier)s_locals *asyncgen_heap = \
(struct %(function_identifier)s_locals *)asyncgen->m_heap_storage;""" % {
            "function_identifier" : function_identifier
        }
    else:
        heap_declaration = ""

    return template_asyncgen_object_body_template % {
        "function_identifier"   : function_identifier,
        "function_body"         : indented(function_codes.codes),
        "heap_declaration"      : indented(heap_declaration),
        "function_local_types"  : indented(local_type_decl),
        "function_var_inits"    : indented(function_locals),
        "function_dispatch"     : indented(getYieldReturnDispatchCode(context)),
        "asyncgen_exit"         : generator_exit,
        "asyncgen_module"       : getModuleAccessCode(context),
        "asyncgen_name_obj"     : context.getConstantCode(
            constant = asyncgen_object_body.getFunctionName()
        ),
        "asyncgen_qualname_obj" : getFunctionQualnameObj(asyncgen_object_body, context),
        "code_identifier"       : context.getCodeObjectHandle(
            code_object = asyncgen_object_body.getCodeObject(),
        ),
        "closure_count"         : len(closure_variables)
    }


def generateMakeAsyncgenObjectCode(to_name, expression, emit, context):
    asyncgen_object_body = expression.getAsyncgenRef().getFunctionBody()

    closure_variables = expression.getClosureVariableVersions()

    closure_copy = getClosureCopyCode(
        to_name           = to_name,
        closure_type      = "struct Nuitka_AsyncgenObject *",
        closure_variables = closure_variables,
        context           = context
    )

    emit(
        template_make_asyncgen % {
            "to_name"               : to_name,
            "asyncgen_identifier"   : asyncgen_object_body.getCodeName(),
            "closure_copy"          : indented(closure_copy, 0, True),
        }
    )

    context.addCleanupTempName(to_name)
